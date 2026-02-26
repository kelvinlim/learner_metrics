#!/bin/bash
# Blue-green nginx upstream switcher
# Usage: ./scripts/switch-color.sh [blue|green]
set -e

COLOR="${1:-blue}"
UPSTREAM_CONF="$(cd "$(dirname "$0")/.." && pwd)/nginx/active-upstream.conf"

case "$COLOR" in
  blue)  BACKEND_PORT=8001; FRONTEND_PORT=5001 ;;
  green) BACKEND_PORT=8002; FRONTEND_PORT=5002 ;;
  *)     echo "Usage: $0 [blue|green]"; exit 1 ;;
esac

echo "Switching to $COLOR (backend=$BACKEND_PORT, frontend=$FRONTEND_PORT)..."

cat > "$UPSTREAM_CONF" <<EOF
# Active color: ${COLOR} — managed by scripts/switch-color.sh — DO NOT EDIT MANUALLY
upstream learner_backend  { server 127.0.0.1:${BACKEND_PORT}; }
upstream learner_frontend { server 127.0.0.1:${FRONTEND_PORT}; }
EOF

sudo nginx -t && sudo nginx -s reload
echo "Done — active color: $COLOR"
