#!/usr/bin/env bash
set -euo pipefail

NATIVE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NATIVE_ENV_FILE="${NATIVE_ENV_FILE:-$NATIVE_ROOT/.env.native}"

if [[ -f "$NATIVE_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$NATIVE_ENV_FILE"
  set +a
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
NATIVE_VENV="${NATIVE_VENV:-$NATIVE_ROOT/.venv}"
NATIVE_PYTHON="${NATIVE_PYTHON:-$NATIVE_VENV/bin/python}"
NATIVE_RUN_DIR="${NATIVE_RUN_DIR:-$NATIVE_ROOT/.run/native}"
NATIVE_HTTP_PORT="${NATIVE_HTTP_PORT:-${HTTP_PORT:-18080}}"

# Host services. PostgreSQL normally runs as a systemd unit; Redis is started as
# a dev-managed process by native_ctl.sh because sandboxed hosts cannot run the
# packaged redis-server unit (systemd fails to set up user namespacing for
# User=redis, i.e. status=217/USER).
NATIVE_PG_HOST="${NATIVE_PG_HOST:-127.0.0.1}"
NATIVE_PG_PORT="${NATIVE_PG_PORT:-5432}"
NATIVE_REDIS_HOST="${NATIVE_REDIS_HOST:-127.0.0.1}"
NATIVE_REDIS_PORT="${NATIVE_REDIS_PORT:-6379}"
NATIVE_REDIS_DIR="${NATIVE_REDIS_DIR:-$NATIVE_RUN_DIR/redis}"
NATIVE_REDIS_SERVER="${NATIVE_REDIS_SERVER:-redis-server}"
NATIVE_REDIS_CLI="${NATIVE_REDIS_CLI:-redis-cli}"

if [[ "${PROJECTS_ROOT:-}" != /* ]]; then
  PROJECTS_ROOT="${PROJECTS_ROOT:-$NATIVE_ROOT/projects}"
  PROJECTS_ROOT="$NATIVE_ROOT/${PROJECTS_ROOT#./}"
fi
if [[ "${PRESETS_ROOT:-}" != /* ]]; then
  PRESETS_ROOT="${PRESETS_ROOT:-$NATIVE_ROOT/presets}"
  PRESETS_ROOT="$NATIVE_ROOT/${PRESETS_ROOT#./}"
fi
if [[ "${PRESET_SCHEMA_PATH:-}" != /* ]]; then
  PRESET_SCHEMA_PATH="${PRESET_SCHEMA_PATH:-$NATIVE_ROOT/schemas/preset.schema.json}"
  PRESET_SCHEMA_PATH="$NATIVE_ROOT/${PRESET_SCHEMA_PATH#./}"
fi

export APP_ENV="${APP_ENV:-development}"
export APP_VERSION="${APP_VERSION:-0.1.0-m1}"
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://novel:novel-m0-dev-password@127.0.0.1:5432/novel}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export PROJECTS_ROOT PRESETS_ROOT PRESET_SCHEMA_PATH
export GIT_USER_NAME="${GIT_USER_NAME:-Novel Agent Platform}"
export GIT_USER_EMAIL="${GIT_USER_EMAIL:-novel-agent-platform@localhost}"
export WORKER_HEARTBEAT_KEY="${WORKER_HEARTBEAT_KEY:-novel:worker:heartbeat}"
export WORKER_HEARTBEAT_TTL_SECONDS="${WORKER_HEARTBEAT_TTL_SECONDS:-30}"
export WORKER_HEARTBEAT_INTERVAL_SECONDS="${WORKER_HEARTBEAT_INTERVAL_SECONDS:-5}"
export WORKER_ID="${WORKER_ID:-novel-worker-native}"
export HTTP_PORT="$NATIVE_HTTP_PORT"
export PYTHONPATH="$NATIVE_ROOT/backend/src${PYTHONPATH:+:$PYTHONPATH}"

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "[native] missing command: $command_name" >&2
    return 1
  fi
}

require_venv() {
  if [[ ! -x "$NATIVE_PYTHON" ]]; then
    echo "[native] virtualenv is missing: $NATIVE_VENV" >&2
    echo "[native] run: make native-install" >&2
    return 1
  fi
}

pid_file() {
  printf '%s/%s.pid\n' "$NATIVE_RUN_DIR" "$1"
}

log_file() {
  printf '%s/%s.log\n' "$NATIVE_RUN_DIR" "$1"
}

is_running() {
  local pid_path="$1"
  [[ -s "$pid_path" ]] || return 1
  local pid
  pid="$(<"$pid_path")"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

postgres_ready() {
  command -v pg_isready >/dev/null 2>&1 || return 1
  pg_isready -h "$NATIVE_PG_HOST" -p "$NATIVE_PG_PORT" -q >/dev/null 2>&1
}

redis_ready() {
  command -v "$NATIVE_REDIS_CLI" >/dev/null 2>&1 || return 1
  [[ "$("$NATIVE_REDIS_CLI" -h "$NATIVE_REDIS_HOST" -p "$NATIVE_REDIS_PORT" ping 2>/dev/null)" == "PONG" ]]
}

require_postgres() {
  if postgres_ready; then
    return 0
  fi
  echo "[native] PostgreSQL is not accepting connections on ${NATIVE_PG_HOST}:${NATIVE_PG_PORT}" >&2
  echo "[native] start it with: sudo systemctl start postgresql" >&2
  echo "[native] first-time setup: make native-provision" >&2
  return 1
}
