# syntax=docker/dockerfile:1.7

# --- Stage 1: build the SvelteKit frontend ---
FROM node:20.18-alpine AS frontend-build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: python runtime ---
FROM python:3.12.7-slim-bookworm AS runtime

# uv copied from official slim image — avoids pip-bootstrap cost.
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

# libpq5 covers asyncpg's runtime symbol resolution; curl is for HEALTHCHECK.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/pyproject.toml backend/alembic.ini ./
COPY backend/src ./src

RUN uv pip install --system --no-cache .

# Frontend build artifacts → /app/static; FastAPI serves them via
# StaticFiles + SPA-fallback handler in main.py.
COPY --from=frontend-build /src/build /app/static

COPY backend/scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p /app/data

ENV OPENCLEF_STATIC_DIR=/app/static \
    OPENCLEF_DATA_DIR=/app/data \
    PYTHONUNBUFFERED=1

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
