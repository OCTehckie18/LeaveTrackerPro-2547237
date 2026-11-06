#!/bin/sh
# Container entrypoint: migrate, (demo only) seed, then serve. Safe with exactly one API instance.
set -e
alembic upgrade head
if [ "$DEMO_MODE" = "true" ]; then
  python -m app.cli seed
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --no-server-header --no-proxy-headers
