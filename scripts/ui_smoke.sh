#!/usr/bin/env bash
# Spawn an isolated instance and run the headless UI smoke against it.
#
# The instance gets its own DATA_DIR and port so it never touches the
# production container on 15000:
#
#     scripts/ui_smoke.sh                      # defaults
#     scripts/ui_smoke.sh --headed             # pass flags through to ui_smoke.py
#     SMOKE_PORT=16999 scripts/ui_smoke.sh
#
# Requires: uv sync --frozen (playwright is a dev dependency)
#           + .venv/bin/playwright install chromium
#           (NOT `uv run playwright ...` — non-frozen re-resolution can pick the
#            wrong platform wheel, see fix-mimo.md §7.5 #8)
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${SMOKE_PORT:-15999}"
DATA_DIR="${SMOKE_DATA_DIR:-/tmp/opencode/ui-smoke-data}"
BASE_URL="http://127.0.0.1:${PORT}"

case "$DATA_DIR" in
  /tmp/opencode/*|*/ui-smoke-data) : ;;          # only ever wipe a dedicated smoke dir
  *) echo "refusing to wipe DATA_DIR=$DATA_DIR" >&2; exit 2 ;;
esac

if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
  echo "port $PORT already serves /health - refusing to run against a foreign instance" >&2
  exit 2
fi

rm -rf "$DATA_DIR"
mkdir -p "$DATA_DIR"

echo ">> starting isolated instance on $BASE_URL (DATA_DIR=$DATA_DIR)"
DATA_DIR="$DATA_DIR" uv run uvicorn backend.main:app --host 127.0.0.1 --port "$PORT" \
  --log-level warning &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

ready=0
for _ in $(seq 1 40); do
  if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then ready=1; break; fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then echo "server exited early" >&2; exit 1; fi
  sleep 0.5
done
if [ "$ready" != 1 ]; then echo "server never became ready" >&2; exit 1; fi

echo ">> running headless smoke"
uv run python scripts/ui_smoke.py --base-url "$BASE_URL" "$@"
