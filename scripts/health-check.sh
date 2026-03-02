#!/usr/bin/env sh
# Health check for external monitoring (cron, Uptime Kuma, etc.).
# Uses /health (no auth) for liveness. Exit 0 = ok, 1 = failure.

set -e

API_URL="${API_URL:-http://localhost:8000}"

code=$(curl -sf -o /dev/null -w "%{http_code}" --connect-timeout 5 "${API_URL}/health" 2>/dev/null || echo "000")

if [ "$code" = "200" ]; then
  echo "OK: ${API_URL}/health returned 200"
  exit 0
else
  echo "FAIL: ${API_URL}/health returned ${code:-connection failed}"
  exit 1
fi
