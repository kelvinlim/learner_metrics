#!/bin/bash
set -e

echo "Running database migrations..."
cd /app/backend && alembic upgrade head

echo "Starting Learner Metrics API (dev)..."
cd /app && exec uvicorn backend.main:app --host 0.0.0.0 --port ${BACKEND_PORT:-8020} --reload
