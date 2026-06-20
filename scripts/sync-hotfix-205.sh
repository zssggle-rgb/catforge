#!/usr/bin/env bash
set -euo pipefail

target="${1:-dev}"
env_file="${CATFORGE_ENV_FILE:-.catforge/deploy-${target}.env}"

usage() {
  echo "Usage: $0 [dev|test]"
  echo "Sync the current committed Git revision to 205 and hot-fix API Python source without rebuilding images."
  echo "Use scripts/deploy.sh for dependency, Dockerfile, migration, or frontend changes."
}

if [[ "${target}" == "-h" || "${target}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -f "${env_file}" ]]; then
  echo "Missing deployment env file: ${env_file}" >&2
  echo "Create it from .env.example and keep real values under .catforge/." >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "${env_file}"
set +a

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required variable: ${name}" >&2
    exit 2
  fi
}

shell_quote() {
  printf "%q" "$1"
}

require_var CATFORGE_DEPLOY_HOST
require_var CATFORGE_DEPLOY_USER
require_var CATFORGE_SSH_KEY

app_dir="${CATFORGE_APP_DIR:-/opt/catforge}"
compose_file="${CATFORGE_COMPOSE_FILE:-docker-compose.cloud.yml}"
api_port="${CATFORGE_API_PORT:-8000}"
git_remote="${CATFORGE_GIT_REMOTE:-origin}"
current_branch="$(git branch --show-current)"
git_ref="${CATFORGE_HOTFIX_GIT_REF:-${current_branch}}"
git_repo="${CATFORGE_GIT_REPO:-$(git config --get "remote.${git_remote}.url" || true)}"
git_timeout="${CATFORGE_GIT_TIMEOUT:-20}"
push_to_github="${CATFORGE_HOTFIX_PUSH:-true}"
bundle_fallback="${CATFORGE_HOTFIX_BUNDLE_FALLBACK:-true}"
install_claude_skills="${CATFORGE_HOTFIX_INSTALL_CLAUDE_SKILLS:-true}"
restart_api="${CATFORGE_HOTFIX_RESTART_API:-true}"
smoke_command="${CATFORGE_HOTFIX_SMOKE_COMMAND:-}"

if [[ -z "${git_ref}" ]]; then
  echo "Cannot infer Git ref from detached HEAD. Set CATFORGE_GIT_REF." >&2
  exit 2
fi
if [[ -z "${git_repo}" ]]; then
  echo "Cannot infer Git repository URL. Set CATFORGE_GIT_REPO." >&2
  exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is not clean. Commit or stash changes before hot-fixing 205." >&2
  git status --short >&2
  exit 3
fi
if [[ "${push_to_github}" == "true" && "${current_branch}" != "${git_ref}" ]]; then
  echo "Current branch (${current_branch}) does not match CATFORGE_HOTFIX_GIT_REF (${git_ref})." >&2
  echo "Push manually and set CATFORGE_HOTFIX_PUSH=false, or set CATFORGE_HOTFIX_GIT_REF=${current_branch}." >&2
  exit 3
fi

commit_sha="$(git rev-parse "${git_ref}")"
short_sha="$(git rev-parse --short "${commit_sha}")"
ssh_opts=(-i "${CATFORGE_SSH_KEY}" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new)
remote="${CATFORGE_DEPLOY_USER}@${CATFORGE_DEPLOY_HOST}"

echo "Hot-fix target: ${remote}:${app_dir}"
echo "Git ref: ${git_ref} (${short_sha})"

if [[ "${push_to_github}" == "true" ]]; then
  echo "Pushing ${git_ref} to ${git_remote}"
  git push "${git_remote}" "${git_ref}"
fi

sync_via_github() {
  ssh "${ssh_opts[@]}" "${remote}" \
    "APP_DIR=$(shell_quote "${app_dir}") GIT_REPO=$(shell_quote "${git_repo}") GIT_REF=$(shell_quote "${git_ref}") COMMIT_SHA=$(shell_quote "${commit_sha}") GIT_TIMEOUT=$(shell_quote "${git_timeout}") bash -s" <<'REMOTE'
set -euo pipefail

if [[ ! -d "${APP_DIR}/.git" ]]; then
  mkdir -p "${APP_DIR}"
  tmp_dir="$(mktemp -d /tmp/catforge-git-sync.XXXXXX)"
  trap 'rm -rf "${tmp_dir}"' EXIT
  timeout "${GIT_TIMEOUT}" git clone --branch "${GIT_REF}" "${GIT_REPO}" "${tmp_dir}"
  find "${APP_DIR}" -mindepth 1 -maxdepth 1 ! -name .env -exec rm -rf {} +
  shopt -s dotglob nullglob
  mv "${tmp_dir}"/* "${APP_DIR}/"
  shopt -u dotglob nullglob
fi

cd "${APP_DIR}"
git remote set-url origin "${GIT_REPO}"
if ! timeout "${GIT_TIMEOUT}" git fetch --prune origin "${GIT_REF}"; then
  exit 42
fi
git checkout -B "${GIT_REF}" "${COMMIT_SHA}"
git reset --hard "${COMMIT_SHA}"
git clean -fd -e .env -e .catforge/
git rev-parse --short HEAD
REMOTE
}

sync_via_bundle() {
  local bundle_path remote_bundle
  bundle_path="$(mktemp "${TMPDIR:-/tmp}/catforge-hotfix.XXXXXX.bundle")"
  remote_bundle="/tmp/catforge-${short_sha}.bundle"
  trap 'rm -f "${bundle_path}"' RETURN
  git bundle create "${bundle_path}" "${git_ref}"
  scp "${ssh_opts[@]}" "${bundle_path}" "${remote}:${remote_bundle}"
  ssh "${ssh_opts[@]}" "${remote}" \
    "APP_DIR=$(shell_quote "${app_dir}") GIT_REF=$(shell_quote "${git_ref}") COMMIT_SHA=$(shell_quote "${commit_sha}") REMOTE_BUNDLE=$(shell_quote "${remote_bundle}") bash -s" <<'REMOTE'
set -euo pipefail
cd "${APP_DIR}"
git fetch "${REMOTE_BUNDLE}" "${GIT_REF}:refs/remotes/origin/${GIT_REF}"
git checkout -B "${GIT_REF}" "${COMMIT_SHA}"
git reset --hard "${COMMIT_SHA}"
git clean -fd -e .env -e .catforge/
rm -f "${REMOTE_BUNDLE}"
git rev-parse --short HEAD
REMOTE
}

if sync_via_github; then
  echo "Remote sync method: github"
else
  sync_rc=$?
  if [[ "${bundle_fallback}" != "true" ]]; then
    echo "GitHub sync failed with exit code ${sync_rc}; bundle fallback is disabled." >&2
    exit "${sync_rc}"
  fi
  echo "GitHub sync failed with exit code ${sync_rc}; using git bundle fallback."
  sync_via_bundle
  echo "Remote sync method: bundle"
fi

if [[ "${install_claude_skills}" == "true" ]]; then
  echo "Installing Claude Code skills when permissions allow"
  ssh "${ssh_opts[@]}" "${remote}" "APP_DIR=$(shell_quote "${app_dir}") bash -s" <<'REMOTE'
set -euo pipefail
cd "${APP_DIR}"

install_skill_dir() {
  local target_home="$1"
  if [[ ! -d "${target_home}" ]]; then
    return 0
  fi
  mkdir -p "${target_home}/.claude/skills"
  for skill_dir in tools/claude/skills/catforge-*; do
    [[ -d "${skill_dir}" ]] || continue
    skill_name="$(basename "${skill_dir}")"
    rm -rf "${target_home}/.claude/skills/${skill_name}"
    cp -R "${skill_dir}" "${target_home}/.claude/skills/${skill_name}"
  done
}

if [[ "$(id -u)" == "0" ]]; then
  install_skill_dir /root
  install_skill_dir /home/deploy
  chown -R deploy:deploy /home/deploy/.claude 2>/dev/null || true
else
  install_skill_dir "${HOME}"
  if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    sudo bash -c 'cd "$1"; mkdir -p /root/.claude/skills /home/deploy/.claude/skills; for skill_dir in tools/claude/skills/catforge-*; do [[ -d "${skill_dir}" ]] || continue; skill_name="$(basename "${skill_dir}")"; rm -rf "/root/.claude/skills/${skill_name}" "/home/deploy/.claude/skills/${skill_name}"; cp -R "${skill_dir}" "/root/.claude/skills/${skill_name}"; cp -R "${skill_dir}" "/home/deploy/.claude/skills/${skill_name}"; done; chown -R deploy:deploy /home/deploy/.claude 2>/dev/null || true' _ "${APP_DIR}"
  else
    echo "No passwordless sudo; installed skills only for ${HOME}." >&2
  fi
fi
REMOTE
fi

if [[ "${restart_api}" == "true" ]]; then
  echo "Hot-fixing API container source without image rebuild"
  ssh "${ssh_opts[@]}" "${remote}" \
    "APP_DIR=$(shell_quote "${app_dir}") COMPOSE_FILE=$(shell_quote "${compose_file}") bash -s" <<'REMOTE'
set -euo pipefail
cd "${APP_DIR}"

if [[ ! -f ".env" ]]; then
  echo "Missing remote runtime env: ${APP_DIR}/.env" >&2
  exit 2
fi

api_container="$(docker compose -f "${COMPOSE_FILE}" --env-file .env ps -q api)"
if [[ -z "${api_container}" ]]; then
  echo "API container is not running. Use scripts/deploy.sh first." >&2
  exit 3
fi

docker cp "${APP_DIR}/apps/api-server/app/." "${api_container}:/app/app/"
docker compose -f "${COMPOSE_FILE}" --env-file .env restart api
docker compose -f "${COMPOSE_FILE}" --env-file .env ps api
REMOTE
fi

echo "Checking server-local API readiness"
ssh "${ssh_opts[@]}" "${remote}" "API_PORT=$(shell_quote "${api_port}") bash -s" <<'REMOTE'
set -euo pipefail
for attempt in {1..20}; do
  if curl -fsS --max-time 5 "http://127.0.0.1:${API_PORT}/readyz"; then
    exit 0
  fi
  sleep 1
done
echo "API readyz did not become ready in time" >&2
exit 4
REMOTE
echo

if [[ -n "${smoke_command}" ]]; then
  smoke_b64="$(printf "%s" "${smoke_command}" | base64 | tr -d '\n')"
  echo "Running API smoke command"
  ssh "${ssh_opts[@]}" "${remote}" \
    "APP_DIR=$(shell_quote "${app_dir}") COMPOSE_FILE=$(shell_quote "${compose_file}") SMOKE_B64=$(shell_quote "${smoke_b64}") bash -s" <<'REMOTE'
set -euo pipefail
cd "${APP_DIR}"
smoke_command="$(printf "%s" "${SMOKE_B64}" | base64 -d)"
docker compose -f "${COMPOSE_FILE}" --env-file .env exec -T api bash -lc "${smoke_command}"
REMOTE
fi

echo "API hot-fix complete: ${target} (${short_sha})"
