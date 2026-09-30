#!/usr/bin/env bash
# Regression guard: the backend must read the wall clock only through clock.py,
# otherwise the test clock mock (clock.set_mock_time) silently stops working and
# timezone handling regresses (the original P1-02 bug).
set -euo pipefail
cd "$(dirname "$0")/.."

matches="$(grep -rnE 'date\.today\(\)|datetime\.now\(\)|datetime\.today\(\)|utcnow\(\)' backend/ \
  --include='*.py' | grep -v '^backend/clock.py:' || true)"

if [ -n "$matches" ]; then
  echo "Raw clock usage found outside backend/clock.py:" >&2
  echo "$matches" >&2
  exit 1
fi

echo "clock usage OK: all reads go through backend/clock.py"
