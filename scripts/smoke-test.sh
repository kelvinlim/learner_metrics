#!/bin/bash
# Basic smoke tests
# Usage: ./scripts/smoke-test.sh [dev|staging|blue|green]
set -e

ENV="${1:-dev}"

case "$ENV" in
    dev)     BASE_URL="http://localhost:8020" ;;
    staging) BASE_URL="http://localhost:8010" ;;
    blue)    BASE_URL="http://localhost:8001" ;;
    green)   BASE_URL="http://localhost:8002" ;;
    *)       echo "Unknown env: $ENV"; exit 1 ;;
esac

echo "Smoke testing $ENV at $BASE_URL..."

# Health check
STATUS=$(curl -sf "$BASE_URL/health" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))")
if [[ "$STATUS" != "ok" && "$STATUS" != "degraded" ]]; then
    echo "FAIL: /health returned unexpected status: $STATUS"
    exit 1
fi
echo "  /health: $STATUS"

# Docs endpoint
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/docs")
if [[ "$HTTP_CODE" != "200" ]]; then
    echo "FAIL: /docs returned $HTTP_CODE"
    exit 1
fi
echo "  /docs: 200"

echo "All smoke tests passed for $ENV."
