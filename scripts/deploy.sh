#!/bin/bash
# Blue-green production deploy
# Usage: ./scripts/deploy.sh [blue|green]
set -e

COLOR="${1:-blue}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "$COLOR" != "blue" && "$COLOR" != "green" ]]; then
    echo "Usage: $0 [blue|green]"
    exit 1
fi

echo "=== Deploying to $COLOR ==="

# Build and start target color containers
cd "$PROJECT_DIR"
podman-compose -f "docker-compose.prod-${COLOR}.yml" up -d --build

# Health check — wait up to 60s for backend to be ready
if [[ "$COLOR" == "blue" ]]; then
    BACKEND_PORT=8001
else
    BACKEND_PORT=8002
fi

echo "Waiting for backend health check on port $BACKEND_PORT..."
for i in $(seq 1 30); do
    if curl -sf "http://localhost:${BACKEND_PORT}/health" > /dev/null 2>&1; then
        echo "Backend is healthy."
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo "ERROR: Backend health check timed out. Aborting."
        exit 1
    fi
    sleep 2
done

# Switch nginx to new color
bash "$PROJECT_DIR/scripts/switch-color.sh" "$COLOR"

echo "=== Deploy complete — active color: $COLOR ==="
echo "Previous color containers still running for rollback."
echo "To rollback: ./scripts/switch-color.sh [previous-color]"
