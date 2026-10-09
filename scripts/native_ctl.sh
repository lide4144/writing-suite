#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/native_common.sh"

action="${1:-status}"
mkdir -p "$NATIVE_RUN_DIR" "$PROJECTS_ROOT"

start_process() {
  local name="$1"
  local workdir="$2"
  shift 2
  local pid_path
  pid_path="$(pid_file "$name")"
  if is_running "$pid_path"; then
    echo "[native] $name is already running (pid $(<"$pid_path"))"
    return 0
  fi
  rm -f "$pid_path"
  echo "[native] starting $name"
  # setsid puts the service in its own session/process group so stop_process can
  # signal the whole tree. Without it, killing a wrapper such as `npm run start`
  # leaves the real node server orphaned and holding its port.
  (
    cd "$workdir"
    exec setsid "$@"
  ) >"$(log_file "$name")" 2>&1 < /dev/null &
  printf '%s\n' "$!" >"$pid_path"
  sleep 1
  if ! is_running "$pid_path"; then
    echo "[native] $name exited during startup; see $(log_file "$name")" >&2
    return 1
  fi
}

stop_process() {
  local name="$1"
  local pid_path
  pid_path="$(pid_file "$name")"
  if ! is_running "$pid_path"; then
    rm -f "$pid_path"
    return 0
  fi
  local pid
  pid="$(<"$pid_path")"
  echo "[native] stopping $name (pid $pid)"
  # Negative PID targets the whole process group created by setsid.
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 50); do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$pid_path"
      return 0
    fi
    sleep 0.2
  done
  echo "[native] $name ignored SIGTERM; sending SIGKILL" >&2
  kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  rm -f "$pid_path"
  return 0
}

start_infra() {
  require_postgres
  if redis_ready; then
    echo "[native] redis is already running on ${NATIVE_REDIS_HOST}:${NATIVE_REDIS_PORT}"
    return 0
  fi
  require_command "$NATIVE_REDIS_CLI"

  # Prefer the host service: it survives reboots and restarts on failure.
  if command -v systemctl >/dev/null 2>&1 && sudo -n systemctl start redis-server 2>/dev/null; then
    for _ in $(seq 1 25); do
      if redis_ready; then
        echo "[native] started system redis-server"
        return 0
      fi
      sleep 0.2
    done
  fi

  # Fallback for hosts where the packaged unit cannot run; see
  # docs/DEV_ENVIRONMENT.md for the observed systemd failure and the drop-in.
  require_command "$NATIVE_REDIS_SERVER"
  mkdir -p "$NATIVE_REDIS_DIR"
  start_process redis "$NATIVE_ROOT" "$NATIVE_REDIS_SERVER" \
    --port "$NATIVE_REDIS_PORT" \
    --bind "$NATIVE_REDIS_HOST" \
    --dir "$NATIVE_REDIS_DIR" \
    --save "" \
    --appendonly no
  for _ in $(seq 1 25); do
    if redis_ready; then
      return 0
    fi
    sleep 0.2
  done
  echo "[native] redis did not become ready; see $(log_file redis)" >&2
  return 1
}

start_all() {
  require_venv
  require_command npm
  require_command caddy
  require_command curl
  start_infra
  "$SCRIPT_DIR/native_migrate.sh"
  start_process worker "$NATIVE_ROOT" "$NATIVE_VENV/bin/python" -m novel_agent.worker
  start_process api "$NATIVE_ROOT" "$NATIVE_VENV/bin/uvicorn" novel_agent.main:app --host 127.0.0.1 --port 8000
  start_process frontend "$NATIVE_ROOT/frontend" env NODE_ENV=production HOSTNAME=127.0.0.1 PORT=3000 npm run start
  start_process caddy "$NATIVE_ROOT" caddy run --config "$NATIVE_ROOT/Caddyfile.native" --adapter caddyfile
  echo "[native] stack started at http://127.0.0.1:${HTTP_PORT}"
}

stop_all() {
  # Stop the proxy first so no new requests arrive while app processes exit.
  stop_process caddy
  stop_process frontend
  stop_process api
  stop_process worker
  # Only stops Redis if this stack started it; an externally managed Redis has
  # no pid file and is left running.
  stop_process redis
}

status_all() {
  local failed=0

  if postgres_ready; then
    echo "[native] postgres: ready (${NATIVE_PG_HOST}:${NATIVE_PG_PORT})"
  else
    echo "[native] postgres: unreachable (${NATIVE_PG_HOST}:${NATIVE_PG_PORT}) — sudo systemctl start postgresql"
    failed=1
  fi

  if redis_ready; then
    local managed="external"
    if is_running "$(pid_file redis)"; then
      managed="dev-managed pid $(<"$(pid_file redis)")"
    elif command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet redis-server 2>/dev/null; then
      managed="systemd redis-server.service"
    fi
    echo "[native] redis: ready (${NATIVE_REDIS_HOST}:${NATIVE_REDIS_PORT}, ${managed})"
  else
    echo "[native] redis: unreachable (${NATIVE_REDIS_HOST}:${NATIVE_REDIS_PORT})"
    failed=1
  fi

  for name in worker api frontend caddy; do
    local pid_path
    pid_path="$(pid_file "$name")"
    if is_running "$pid_path"; then
      echo "[native] $name: running (pid $(<"$pid_path"))"
    else
      echo "[native] $name: stopped"
      failed=1
    fi
  done
  return "$failed"
}

case "$action" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    start_all
    ;;
  status)
    status_all
    ;;
  infra)
    start_infra
    ;;
  *)
    echo "usage: $0 {start|stop|restart|status|infra}" >&2
    exit 2
    ;;
esac
