#!/usr/bin/env bash
set -euo pipefail

target="${1:-dev}"
env_file="${CATFORGE_ENV_FILE:-.catforge/deploy-${target}.env}"

usage() {
  echo "Usage: $0 [dev|test]"
  echo "Set CATFORGE_ENV_FILE to use a custom deployment env file."
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

require_var CATFORGE_DEPLOY_HOST
require_var CATFORGE_DEPLOY_USER
require_var CATFORGE_SSH_KEY

app_dir="${CATFORGE_APP_DIR:-/opt/catforge}"
compose_file="${CATFORGE_COMPOSE_FILE:-docker-compose.cloud.yml}"
runtime_env_file="${CATFORGE_RUNTIME_ENV_FILE:-}"
api_port="${CATFORGE_API_PORT:-8000}"
sync_strategy="${CATFORGE_SYNC_STRATEGY:-rsync}"
git_repo="${CATFORGE_GIT_REPO:-}"
git_ref="${CATFORGE_GIT_REF:-main}"
git_depth="${CATFORGE_GIT_DEPTH:-1}"
git_timeout="${CATFORGE_GIT_TIMEOUT:-60}"
ssh_opts=(-i "${CATFORGE_SSH_KEY}" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new)
remote="${CATFORGE_DEPLOY_USER}@${CATFORGE_DEPLOY_HOST}"

if [[ "${sync_strategy}" != "rsync" && "${sync_strategy}" != "github" ]]; then
  echo "Unsupported CATFORGE_SYNC_STRATEGY: ${sync_strategy}" >&2
  echo "Use 'rsync' or 'github'." >&2
  exit 2
fi

if [[ "${sync_strategy}" == "github" ]]; then
  require_var CATFORGE_GIT_REPO
fi

echo "Deploying ${target} to ${remote}:${app_dir} using ${sync_strategy} sync"

if [[ "${sync_strategy}" == "github" ]]; then
  ssh "${ssh_opts[@]}" "${remote}" \
    "APP_DIR='${app_dir}' GIT_REPO='${git_repo}' GIT_REF='${git_ref}' GIT_DEPTH='${git_depth}' GIT_TIMEOUT='${git_timeout}' bash -s" <<'REMOTE_SYNC'
set -euo pipefail

tmp_dir=""
env_backup=""

cleanup() {
  if [[ -n "${tmp_dir}" ]]; then
    rm -rf "${tmp_dir}"
  fi
  if [[ -n "${env_backup}" ]]; then
    rm -f "${env_backup}"
  fi
}
trap cleanup EXIT

if [[ -f "${APP_DIR}/.env" ]]; then
  env_backup="$(mktemp)"
  cp "${APP_DIR}/.env" "${env_backup}"
fi

if [[ -d "${APP_DIR}/.git" ]]; then
  cd "${APP_DIR}"
  git remote set-url origin "${GIT_REPO}"
  timeout "${GIT_TIMEOUT}" git fetch --prune --depth "${GIT_DEPTH}" origin "${GIT_REF}"
  git checkout -B "${GIT_REF}" FETCH_HEAD
  git reset --hard FETCH_HEAD
  git clean -fdx -e .env
else
  mkdir -p "${APP_DIR}"
  tmp_dir="$(mktemp -d /tmp/catforge-git-sync.XXXXXX)"
  timeout "${GIT_TIMEOUT}" git clone --depth "${GIT_DEPTH}" --branch "${GIT_REF}" "${GIT_REPO}" "${tmp_dir}"
  if [[ -n "${env_backup}" ]]; then
    cp "${env_backup}" "${APP_DIR}/.env"
  fi
  find "${APP_DIR}" -mindepth 1 -maxdepth 1 ! -name .env -exec rm -rf {} +
  shopt -s dotglob nullglob
  mv "${tmp_dir}"/* "${APP_DIR}/"
  shopt -u dotglob nullglob
fi
REMOTE_SYNC
else
  ssh "${ssh_opts[@]}" "${remote}" "mkdir -p '${app_dir}'"

  rsync -az --delete \
    -e "ssh -i ${CATFORGE_SSH_KEY} -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new" \
    --exclude ".git/" \
    --exclude ".venv/" \
    --exclude ".pytest_cache/" \
    --exclude "__pycache__/" \
    --exclude "node_modules/" \
    --exclude "dist/" \
    --exclude "data/" \
    --exclude ".catforge/" \
    --exclude ".env" \
    --exclude ".env.*" \
    --exclude "*.log" \
    --exclude "cankao/" \
    ./ "${remote}:${app_dir}/"
fi

if [[ -n "${runtime_env_file}" ]]; then
  if [[ ! -f "${runtime_env_file}" ]]; then
    echo "Missing runtime env file: ${runtime_env_file}" >&2
    exit 2
  fi
  scp "${ssh_opts[@]}" "${runtime_env_file}" "${remote}:${app_dir}/.env"
  ssh "${ssh_opts[@]}" "${remote}" "chmod 600 '${app_dir}/.env'"
fi

ssh "${ssh_opts[@]}" "${remote}" "APP_DIR='${app_dir}' COMPOSE_FILE='${compose_file}' bash -s" <<'REMOTE'
set -euo pipefail
cd "${APP_DIR}"

if [[ ! -f ".env" ]]; then
  echo "Missing remote runtime env: ${APP_DIR}/.env" >&2
  exit 2
fi

docker compose -f "${COMPOSE_FILE}" --env-file .env build
docker compose -f "${COMPOSE_FILE}" --env-file .env run --rm -T api python -m alembic upgrade head </dev/null
docker compose -f "${COMPOSE_FILE}" --env-file .env rm -sf api web
docker compose -f "${COMPOSE_FILE}" --env-file .env up -d --remove-orphans --force-recreate
docker compose -f "${COMPOSE_FILE}" --env-file .env ps
REMOTE

health_url="${CATFORGE_APP_URL:-http://${CATFORGE_DEPLOY_HOST}:${api_port}}"
if command -v curl >/dev/null 2>&1; then
  echo "Checking ${health_url}/healthz"
  if ! curl -fsS --retry 3 --retry-delay 2 --retry-all-errors --max-time 5 "${health_url}/healthz"; then
    echo
    echo "Public healthz unavailable; checking server-local healthz through SSH"
    ssh "${ssh_opts[@]}" "${remote}" "curl -fsS --max-time 5 'http://127.0.0.1:${api_port}/healthz'"
  fi
  echo
  echo "Checking ${health_url}/readyz"
  if ! curl -fsS --retry 3 --retry-delay 2 --retry-all-errors --max-time 5 "${health_url}/readyz"; then
    echo
    echo "Public readyz unavailable; checking server-local readyz through SSH"
    ssh "${ssh_opts[@]}" "${remote}" "curl -fsS --max-time 5 'http://127.0.0.1:${api_port}/readyz'"
  fi
  echo
fi

echo "Deploy complete: ${target}"
