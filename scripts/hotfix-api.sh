#!/usr/bin/env bash
set -euo pipefail

target="${1:-dev}"
env_file="${CATFORGE_ENV_FILE:-.catforge/deploy-${target}.env}"

usage() {
  echo "Usage: $0 [dev|test]"
  echo "Hot-fix Python API source into the running container without rebuilding images."
  echo "Use scripts/deploy.sh when dependencies, migrations, Dockerfiles, or frontend assets changed."
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
api_port="${CATFORGE_API_PORT:-8000}"
ssh_opts=(-i "${CATFORGE_SSH_KEY}" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new)
remote="${CATFORGE_DEPLOY_USER}@${CATFORGE_DEPLOY_HOST}"

echo "Hot-fixing API source on ${remote}:${app_dir}"

rsync -az --delete \
  -e "ssh -i ${CATFORGE_SSH_KEY} -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new" \
  apps/api-server/app/ "${remote}:${app_dir}/apps/api-server/app/"

ssh "${ssh_opts[@]}" "${remote}" "APP_DIR='${app_dir}' COMPOSE_FILE='${compose_file}' bash -s" <<'REMOTE'
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

echo "Checking server-local API readiness"
ssh "${ssh_opts[@]}" "${remote}" "bash -s" <<REMOTE
set -euo pipefail
for attempt in {1..20}; do
  if curl -fsS --max-time 5 'http://127.0.0.1:${api_port}/readyz'; then
    exit 0
  fi
  sleep 1
done
echo "API readyz did not become ready in time" >&2
exit 4
REMOTE
echo
echo "API hot-fix complete: ${target}"
