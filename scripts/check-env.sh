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
api_port="${CATFORGE_API_PORT:-8000}"
ssh_opts=(-i "${CATFORGE_SSH_KEY}" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new)
remote="${CATFORGE_DEPLOY_USER}@${CATFORGE_DEPLOY_HOST}"

echo "Checking ${target} (${remote})"

ssh "${ssh_opts[@]}" "${remote}" "APP_DIR='${app_dir}' bash -s" <<'REMOTE'
set -euo pipefail

echo "host=$(hostname)"
echo "user=$(whoami)"
echo "time=$(date -Is)"

printf 'git='
command -v git

printf 'rsync='
command -v rsync

printf 'docker='
command -v docker
docker --version
docker compose version

printf 'postgresql_service='
systemctl is-active postgresql || true

printf 'postgresql_enabled='
systemctl is-enabled postgresql || true

printf 'postgresql_ready='
pg_isready -h 127.0.0.1 -p 5432 || true

if [[ -d "${APP_DIR}" ]]; then
  echo "app_dir=present:${APP_DIR}"
else
  echo "app_dir=missing:${APP_DIR}"
fi

if [[ -f "${APP_DIR}/.env" ]]; then
  echo "runtime_env=present:${APP_DIR}/.env"
else
  echo "runtime_env=missing:${APP_DIR}/.env"
fi

if [[ -f "${APP_DIR}/docker-compose.cloud.yml" ]]; then
  cd "${APP_DIR}"
  docker compose -f docker-compose.cloud.yml --env-file .env ps || true
fi

if curl -fsS --max-time 5 http://127.0.0.1:8000/healthz >/tmp/catforge-healthz.out 2>/dev/null; then
  echo "local_healthz=$(cat /tmp/catforge-healthz.out)"
else
  echo "local_healthz=unavailable"
fi

if curl -fsS --max-time 5 http://127.0.0.1:8000/readyz >/tmp/catforge-readyz.out 2>/dev/null; then
  echo "local_readyz=$(cat /tmp/catforge-readyz.out)"
else
  echo "local_readyz=unavailable"
fi
REMOTE

health_url="${CATFORGE_APP_URL:-http://${CATFORGE_DEPLOY_HOST}:${api_port}}"
if command -v curl >/dev/null 2>&1; then
  echo "Checking ${health_url}/healthz"
  curl -fsS --max-time 5 "${health_url}/healthz" || echo "healthz unavailable"
  echo
  echo "Checking ${health_url}/readyz"
  curl -fsS --max-time 5 "${health_url}/readyz" || echo "readyz unavailable"
  echo
fi
