#!/usr/bin/env bash
# Shared by the existing cloud deployer and the paired QA deployer.
set -euo pipefail
mode=$1
shift
compose=("$@")
"${compose[@]}" build
"${compose[@]}" run --rm -T api python -m alembic upgrade head </dev/null
if [[ $mode == cloud ]]; then
  "${compose[@]}" rm -sf api web
  "${compose[@]}" up -d --remove-orphans --force-recreate
else
  "${compose[@]}" up -d
fi
"${compose[@]}" ps
