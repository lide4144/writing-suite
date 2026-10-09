#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/native_common.sh"

require_venv
require_command npm

echo "[native] compiling Python source"
"$NATIVE_PYTHON" -m compileall -q "$NATIVE_ROOT/backend/src" "$NATIVE_ROOT/cli/novelctl"

echo "[native] building Next.js standalone output"
(
  cd "$NATIVE_ROOT/frontend"
  # Rebuilding on every `make up` would make the native loop unusable, so rebuild
  # only when the standalone output is missing or older than the frontend source.
  if [[ -f .next/standalone/server.js ]] && \
    [[ -z "$(find app lib public next.config.mjs package.json package-lock.json \
      -newer .next/standalone/server.js 2>/dev/null -print -quit)" ]]; then
    echo "[native] Next.js output is up to date"
  else
    NEXT_PUBLIC_APP_VERSION="$APP_VERSION" npm run build
  fi
)

echo "[native] build complete"
