#!/usr/bin/env bash
# Regression guard: the backend must read the wall clock only through clock.py,
# otherwise the test clock mock (clock.set_mock_time) silently stops working and
# timezone handling regresses (the original P1-02 bug).
#
# Tests are covered too for "what day is it" queries: the host timezone differs
# from Asia/Shanghai for 8 hours a day (16:00-24:00 UTC), so date.today() in a
# test fails on CI while passing locally. Tests may still use datetime.now() to
# measure elapsed time (e.g. the rate limiter window).
set -euo pipefail
cd "$(dirname "$0")/.."

matches="$(grep -rnE 'date\.today\(\)|datetime\.now\(\)|datetime\.today\(\)|utcnow\(\)' backend/ \
  --include='*.py' | grep -v '^backend/clock.py:' || true)"

test_matches="$(grep -rnE 'date\.today\(\)|datetime\.today\(\)|datetime\.now\(\)\.date\(\)|utcnow\(\)' \
  tests/ --include='*.py' || true)"

if [ -n "$matches" ]; then
  echo "Raw clock usage found outside backend/clock.py:" >&2
  echo "$matches" >&2
  exit 1
fi

if [ -n "$test_matches" ]; then
  echo "Host-timezone date queries found in tests/ (use clock.today()):" >&2
  echo "$test_matches" >&2
  exit 1
fi

echo "clock usage OK: backend reads go through backend/clock.py, tests use clock.today()"
