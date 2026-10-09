#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:80}"
HEALTH_URL="${BASE_URL%/}/api/health"

echo "[smoke] waiting for ${HEALTH_URL}"
health_body=""
for attempt in $(seq 1 30); do
  if health_body="$(curl -fsS "$HEALTH_URL" 2>/dev/null)"; then
    break
  fi
  if [[ "$attempt" == "30" ]]; then
    echo "[smoke] health endpoint did not become ready" >&2
    exit 1
  fi
  sleep 2
done

HEALTH_BODY="$health_body" python3 - <<'PY'
import json
import os
import sys

try:
    payload = json.loads(os.environ["HEALTH_BODY"])
except (KeyError, json.JSONDecodeError) as exc:
    print(f"[smoke] invalid health JSON: {exc}", file=sys.stderr)
    raise SystemExit(1)

if payload.get("status") != "ok":
    print(f"[smoke] health is not ok: {payload}", file=sys.stderr)
    raise SystemExit(1)

components = payload.get("components", {})
for component in ("postgres", "redis", "worker"):
    if components.get(component, {}).get("status") != "ok":
        print(f"[smoke] component {component} is not ok: {components.get(component)}", file=sys.stderr)
        raise SystemExit(1)

print("[smoke] health:", json.dumps(payload, ensure_ascii=False))
PY

homepage="$(curl -fsS "${BASE_URL%/}/")"
if [[ "$homepage" != *"Novel Agent Platform"* ]]; then
  echo "[smoke] placeholder homepage marker not found" >&2
  exit 1
fi

preset_body="$(curl -fsS "${BASE_URL%/}/api/v1/presets")"
PRESET_BODY="$preset_body" python3 - <<'PY'
import json
import os
import sys

try:
    presets = json.loads(os.environ["PRESET_BODY"])
except (KeyError, json.JSONDecodeError) as exc:
    print(f"[smoke] invalid preset JSON: {exc}", file=sys.stderr)
    raise SystemExit(1)

names = {item.get("name") for item in presets if isinstance(item, dict)}
required = {"default", "long_novel_high_quality"}
if not required.issubset(names):
    print(f"[smoke] built-in presets are incomplete: {names}", file=sys.stderr)
    raise SystemExit(1)
print("[smoke] built-in presets:", ", ".join(sorted(required)))
PY

running_services="$(docker compose ps --status running --services)"
for service in postgres redis api worker frontend caddy; do
  if ! grep -qx "$service" <<<"$running_services"; then
    echo "[smoke] service is not running: $service" >&2
    exit 1
  fi
done

echo "[smoke] compose services and unified entrypoint are healthy"
