#!/bin/bash
# Staging deploy
# Usage: ./scripts/deploy-staging.sh
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "=== Deploying to staging ==="

podman-compose -f docker-compose.staging.yml up -d --build

echo "Waiting for staging backend..."
for i in $(seq 1 30); do
    if curl -sf "http://localhost:8010/health" > /dev/null 2>&1; then
        echo "Staging backend is healthy."
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo "ERROR: Staging health check timed out."
        exit 1
    fi
    sleep 2
done

bash "$PROJECT_DIR/scripts/smoke-test.sh" staging

echo "=== Staging deploy complete ==="
