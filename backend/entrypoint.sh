#!/bin/sh
set -eu

if [ -n "${DATABASE_URL:-}" ]; then
  echo "Applying database migrations..."
  alembic upgrade head
fi

exec python -m uvicorn backend.main:app \
  --host "${API_HOST:-0.0.0.0}" \
  --port "${API_PORT:-8000}"
