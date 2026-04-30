#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEBAPP_DIR="$ROOT_DIR/uv_intelligent_demo/webapp"
PYTHON_BIN="$ROOT_DIR/venv/bin/python3"

START_STACK=true
STOP_AFTER=false
TIMEOUT_SECONDS="${SMOKE_TEST_TIMEOUT_SECONDS:-150}"
STATE_URL="${SMOKE_TEST_STATE_URL:-http://localhost:8000/api/state}"
HEALTH_URL="${SMOKE_TEST_HEALTH_URL:-http://localhost:8000/api/health}"
TOOLS_URL="${SMOKE_TEST_TOOLS_URL:-http://localhost:8000/api/ai/tools/analysis?limit=20}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-start)
      START_STACK=false
      shift
      ;;
    --stop-after)
      STOP_AFTER=true
      shift
      ;;
    --timeout)
      TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--no-start] [--stop-after] [--timeout SECONDS]" >&2
      exit 2
      ;;
  esac
done

cleanup() {
  if [[ "$STOP_AFTER" == "true" ]]; then
    bash "$WEBAPP_DIR/stop_simulation.sh"
  fi
}
trap cleanup EXIT

if [[ "$START_STACK" == "true" ]]; then
  bash "$WEBAPP_DIR/start_simulation.sh"
fi

if [[ ! -d "$ROOT_DIR/venv" ]]; then
  echo "Error: Virtual environment not found at $ROOT_DIR/venv" >&2
  echo "Please run: python -m venv $ROOT_DIR/venv" >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: Python interpreter not found at $PYTHON_BIN" >&2
  exit 1
fi

export SMOKE_TEST_TIMEOUT_SECONDS="$TIMEOUT_SECONDS"
export STATE_URL
export HEALTH_URL
export TOOLS_URL

"$PYTHON_BIN" - <<'PY'
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


timeout = int(os.environ["SMOKE_TEST_TIMEOUT_SECONDS"])
state_url = os.environ["STATE_URL"]
health_url = os.environ["HEALTH_URL"]
tools_url = os.environ["TOOLS_URL"]


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def parse_iso8601(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


start = time.time()
last_error = None

while time.time() - start < timeout:
    try:
        health = fetch_json(health_url)
        if health.get("status") != "ok":
            last_error = f"Health endpoint returned unexpected payload: {health}"
            time.sleep(2)
            continue

        state = fetch_json(state_url)
        latest = state.get("latest") or {}
        timestamp = latest.get("timestamp")
        if not timestamp:
            last_error = "State endpoint returned no latest telemetry timestamp yet."
            time.sleep(2)
            continue

        event_time = parse_iso8601(timestamp)
        age_seconds = (datetime.now(timezone.utc) - event_time.astimezone(timezone.utc)).total_seconds()
        if age_seconds > 120:
            last_error = f"Latest telemetry is stale ({age_seconds:.1f}s old)."
            time.sleep(2)
            continue

        if latest.get("simulated") is not True:
            last_error = f"Latest telemetry is present but not marked simulated: {latest}"
            time.sleep(2)
            continue

        tools = fetch_json(tools_url)
        samples_used = int(tools.get("samples_used") or 0)
        if samples_used <= 0:
            last_error = f"Tool analysis returned no persisted samples: {tools}"
            time.sleep(2)
            continue

        print("Smoke test passed.")
        print(json.dumps({
            "health": health,
            "latest_timestamp": timestamp,
            "latest_replay_index": latest.get("replay_index"),
            "latest_uv_dose_mj_cm2": latest.get("uv_dose_mj_cm2"),
            "samples_used": samples_used,
        }, indent=2))
        sys.exit(0)
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        last_error = str(exc)
        time.sleep(2)

print("Smoke test failed.", file=sys.stderr)
if last_error:
    print(last_error, file=sys.stderr)
sys.exit(1)
PY
