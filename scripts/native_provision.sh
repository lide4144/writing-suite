#!/usr/bin/env bash
# Idempotent local database provisioning for the native runtime.
#
# Creates the PostgreSQL role, database and pgvector extension that the native
# stack expects. Safe to re-run: existing objects are left untouched.
#
# The role is created as SUPERUSER because Alembic migration 0001 runs
# `CREATE EXTENSION vector`, which requires elevated privileges. This matches
# the Compose behaviour, where POSTGRES_USER is the cluster superuser. Do not
# reuse this role for anything beyond a local trusted machine.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/native_common.sh"

require_command psql

PG_SUPERUSER="${NATIVE_PG_SUPERUSER:-postgres}"
DB_NAME="${POSTGRES_DB:-novel}"
DB_USER="${POSTGRES_USER:-novel}"
DB_PASSWORD="${POSTGRES_PASSWORD:-novel-m0-dev-password}"

# `sudo` needs a terminal to prompt for a password. Set NATIVE_SUDO_FLAGS=-S to
# feed it on stdin (non-interactive automation), or pre-authorize with `sudo -v`.
SUDO=(sudo)
if [[ -n "${NATIVE_SUDO_FLAGS:-}" ]]; then
  # shellcheck disable=SC2206
  SUDO=(sudo ${NATIVE_SUDO_FLAGS})
fi

if ! "${SUDO[@]}" -n true 2>/dev/null && [[ -z "${NATIVE_SUDO_FLAGS:-}" ]]; then
  echo "[native-provision] note: sudo may prompt for your password" >&2
fi

if ! postgres_ready; then
  echo "[native-provision] PostgreSQL is not reachable on ${NATIVE_PG_HOST}:${NATIVE_PG_PORT}" >&2
  echo "[native-provision] start it first: sudo systemctl start postgresql" >&2
  exit 1
fi

run_sql() {
  "${SUDO[@]}" -u "$PG_SUPERUSER" psql -v ON_ERROR_STOP=1 --quiet "$@"
}

echo "[native-provision] ensuring role ${DB_USER}"
run_sql -c "DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN SUPERUSER PASSWORD '${DB_PASSWORD}';
  END IF;
END
\$\$;"

echo "[native-provision] ensuring database ${DB_NAME}"
if [[ "$("${SUDO[@]}" -u "$PG_SUPERUSER" psql -tAc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'")" != "1" ]]; then
  run_sql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
fi

echo "[native-provision] ensuring pgvector extension"
run_sql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "[native-provision] verifying connectivity as ${DB_USER}"
PGPASSWORD="$DB_PASSWORD" psql -h "$NATIVE_PG_HOST" -p "$NATIVE_PG_PORT" -U "$DB_USER" -d "$DB_NAME" \
  -tAc "SELECT current_user || '@' || current_database() || ' vector=' || extversion FROM pg_extension WHERE extname = 'vector';"

# ---------------------------------------------------------------- host services
#
# Debian's redis-server.service sets PrivateUsers=yes. This sandbox's systemd
# cannot set up that user namespace for the unit (status=217/USER, "Failed to
# set up user namespacing"); user namespaces themselves are available here
# (unshare -Ur, bwrap and transient PrivateUsers units all work), so the unit
# needs one hardening flag relaxed. Everything else stays as packaged.
if command -v systemctl >/dev/null 2>&1 && [[ -f /lib/systemd/system/redis-server.service ]]; then
  dropin_dir=/etc/systemd/system/redis-server.service.d
  dropin_file="$dropin_dir/20-private-users.conf"
  if [[ ! -f "$dropin_file" ]]; then
    echo "[native-provision] installing redis-server drop-in (PrivateUsers=no)"
    "${SUDO[@]}" mkdir -p "$dropin_dir"
    printf '%s\n' \
      '[Service]' \
      '# The packaged unit enables PrivateUsers=yes, which systemd cannot set up in' \
      '# this sandbox (status=217/USER). User namespaces themselves work here, so' \
      '# only this flag is relaxed; the rest of the hardening is kept.' \
      'PrivateUsers=no' | "${SUDO[@]}" tee "$dropin_file" >/dev/null
    "${SUDO[@]}" systemctl daemon-reload
  fi
  if ! redis_ready; then
    echo "[native-provision] starting redis-server.service"
    "${SUDO[@]}" systemctl reset-failed redis-server 2>/dev/null || true
    "${SUDO[@]}" systemctl enable --now redis-server >/dev/null 2>&1 || true
    for _ in $(seq 1 25); do
      redis_ready && break
      sleep 0.2
    done
  fi
  if redis_ready; then
    echo "[native-provision] redis is ready ($("$NATIVE_REDIS_CLI" -h "$NATIVE_REDIS_HOST" -p "$NATIVE_REDIS_PORT" ping))"
  else
    echo "[native-provision] warning: redis is not reachable; the native stack will fall back to a dev-managed process" >&2
  fi
fi

echo "[native-provision] done"
