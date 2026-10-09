#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/native_common.sh"

# Prefer the Python 3.12 interpreter the spec targets. `uv python install 3.12`
# (or any other 3.12 on PATH) wins over the distribution default, which is 3.13
# on Debian 13. Both are accepted because the backend only needs >=3.12,<3.14.
if [[ -z "${PYTHON_BIN_SET:-}" && "$PYTHON_BIN" == "python3" ]]; then
  for candidate in python3.12 "$HOME/.local/bin/python3.12"; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

require_command "$PYTHON_BIN"
require_command npm

python_version="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "[native] using $PYTHON_BIN (Python $python_version)"
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(not (sys.version_info >= (3, 12) and sys.version_info < (3, 14)))'; then
  echo "[native] Python $python_version found; native runtime requires Python 3.12 or 3.13." >&2
  exit 1
fi

if [[ ! -d "$NATIVE_VENV" ]]; then
  echo "[native] creating $NATIVE_VENV with $PYTHON_BIN"
  "$PYTHON_BIN" -m venv "$NATIVE_VENV"
fi

echo "[native] installing backend and CLI in editable mode"
"$NATIVE_PYTHON" -m pip install -e "$NATIVE_ROOT/backend[test]" -e "$NATIVE_ROOT/cli"

echo "[native] installing frontend dependencies"
(
  cd "$NATIVE_ROOT/frontend"
  # `npm ci` wipes and reinstalls node_modules, so skip it while the lockfile is
  # unchanged since the last install.
  if [[ -f node_modules/.package-lock.json && node_modules/.package-lock.json -nt package-lock.json ]]; then
    echo "[native] frontend dependencies are up to date"
  else
    npm ci
  fi
)

echo "[native] source dependencies are ready"
