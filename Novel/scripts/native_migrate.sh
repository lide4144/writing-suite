#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/native_common.sh"

require_venv
mkdir -p "$PROJECTS_ROOT"

echo "[native] applying Alembic migrations"
(
  cd "$NATIVE_ROOT"
  "$NATIVE_VENV/bin/alembic" -c backend/alembic.ini upgrade head
  "$NATIVE_PYTHON" -m novel_agent.bootstrap
)

echo "[native] migration and built-in preset bootstrap complete"
