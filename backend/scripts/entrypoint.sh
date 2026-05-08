#!/bin/sh
set -eu

# Auto-migrate on startup. Fails-loudly-and-exits if alembic errors,
# which is desired — a container that boots with a stale schema would
# corrupt invariants downstream tickets depend on.
if [ "${OPENCLEF_AUTO_MIGRATE:-true}" = "true" ]; then
  echo "[entrypoint] alembic upgrade head"
  alembic upgrade head
fi

exec uvicorn openclef.main:app --host 0.0.0.0 --port 8000 "$@"
