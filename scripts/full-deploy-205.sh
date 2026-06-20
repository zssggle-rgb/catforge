#!/usr/bin/env bash
set -euo pipefail

target="${1:-dev}"

if [[ "${target}" == "-h" || "${target}" == "--help" ]]; then
  echo "Usage: $0 [dev|test]"
  echo "Run the full CatForge deploy path: sync code, build images, run migrations, and recreate services."
  echo "For day-to-day API Python changes, use scripts/sync-hotfix-205.sh instead."
  exit 0
fi

echo "Full deploy selected for ${target}; this rebuilds images and may take several minutes."
echo "Use scripts/sync-hotfix-205.sh ${target} for committed API Python hot-fixes."

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${script_dir}/deploy.sh" "${target}"
