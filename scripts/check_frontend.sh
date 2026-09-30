#!/usr/bin/env bash
# Frontend checks that run without a browser:
#   1. syntax-check every ES module the page loads
#   2. run the pure-helper unit assertions
set -euo pipefail
cd "$(dirname "$0")/.."

NODE="${NODE:-node}"

for f in frontend/app.js frontend/lib/*.js frontend/views/*.js; do
  $NODE --check "$f"
done

$NODE scripts/check_template_bindings.mjs
TZ="${TZ:-Asia/Shanghai}" $NODE scripts/frontend_unit.mjs
echo "frontend checks OK"
