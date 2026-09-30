#!/usr/bin/env bash
# Assert that the Python and JavaScript date/week/emoji implementations agree.
#
# The two stacks can't share one implementation without a round trip, so instead
# of duplicating silently we diff both against each other on every CI run.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if [ -x .venv/bin/python ]; then
    PYTHON=.venv/bin/python
  elif command -v uv >/dev/null 2>&1; then
    PYTHON="uv run --no-sync python"
  else
    PYTHON=python3
  fi
fi

NODE="${NODE:-node}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

$PYTHON scripts/parity_backend.py >"$tmp/backend.txt"
$NODE scripts/parity_frontend.mjs >"$tmp/frontend.txt"

if ! diff -u "$tmp/backend.txt" "$tmp/frontend.txt" >"$tmp/diff.txt"; then
  echo "PARITY MISMATCH: frontend and backend logic diverged" >&2
  head -40 "$tmp/diff.txt" >&2
  exit 1
fi

echo "parity OK: $(wc -l <"$tmp/backend.txt") cases match"
