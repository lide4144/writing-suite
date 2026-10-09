#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/native_common.sh"

BASE_URL="${BASE_URL:-http://127.0.0.1:${HTTP_PORT}}"
HEALTH_URL="${BASE_URL%/}/api/health"

require_command curl
require_command python3

echo "[native-smoke] waiting for ${HEALTH_URL}"
health_body=""
for attempt in $(seq 1 30); do
  if health_body="$(curl -fsS "$HEALTH_URL" 2>/dev/null)"; then
    break
  fi
  if [[ "$attempt" == "30" ]]; then
    echo "[native-smoke] health endpoint did not become ready" >&2
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
    print(f"[native-smoke] invalid health JSON: {exc}", file=sys.stderr)
    raise SystemExit(1)

if payload.get("status") != "ok":
    print(f"[native-smoke] health is not ok: {payload}", file=sys.stderr)
    raise SystemExit(1)

components = payload.get("components", {})
for component in ("postgres", "redis", "worker"):
    if components.get(component, {}).get("status") != "ok":
        print(f"[native-smoke] component {component} is not ok: {components.get(component)}", file=sys.stderr)
        raise SystemExit(1)

print("[native-smoke] health:", json.dumps(payload, ensure_ascii=False))
PY

homepage="$(curl -fsS "${BASE_URL%/}/")"
if [[ "$homepage" != *"Novel Agent Platform"* ]]; then
  echo "[native-smoke] placeholder homepage marker not found" >&2
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
    print(f"[native-smoke] invalid preset JSON: {exc}", file=sys.stderr)
    raise SystemExit(1)

names = {item.get("name") for item in presets if isinstance(item, dict)}
required = {"default", "long_novel_high_quality"}
if not required.issubset(names):
    print(f"[native-smoke] built-in presets are incomplete: {names}", file=sys.stderr)
    raise SystemExit(1)
print("[native-smoke] built-in presets:", ", ".join(sorted(required)))
PY

"$SCRIPT_DIR/native_ctl.sh" status
echo "[native-smoke] native source stack and unified entrypoint are healthy"
