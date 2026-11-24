# Development and configuration

Operational detail moved out of the top-level README. For the in-app user
docs, see `frontend/src/routes/docs/`.

## Docker Compose stack

```bash
git clone https://github.com/mekstromjr/openclef.git
cd openclef
cp .env.example .env
docker compose up -d
```

`.env.example` bootstraps a dev admin (`admin` / `password`) on first run.
Those values are deliberately weak and are for local development only. Without
them, the first visit to `/setup` creates the admin account.

| Service | Image | Port |
|---|---|---|
| `app` | built locally from `Dockerfile` | 8000 |
| `worker` | same image, runs `dramatiq openclef.workers.tasks` | (none) |
| `postgres` | `postgres:16.6-alpine` | (internal) |
| `redis` | `redis:7.4-alpine` | (internal) |
| `docs` | Starlight snapshot, `--profile preview` only | 8080 |

The app container runs `alembic upgrade head` on startup (disable with
`OPENCLEF_AUTO_MIGRATE=false`) and then starts uvicorn. The worker shares the
app's data volume, because with the local storage backend the API writes PDFs
there and the worker reads them back to render thumbnails.

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/version
```

Tear down with `docker compose down` (add `-v` to wipe the database and data
volumes).

## Backend (Python 3.12, uv)

```bash
cd backend
uv venv -p 3.12
uv pip install -e '.[dev]'
uv run --no-sync ruff check src tests
uv run --no-sync pytest -q
uv run --no-sync uvicorn openclef.main:app --reload --port 8000
```

Point `OPENCLEF_DATABASE_URL` and `OPENCLEF_REDIS_URL` at a local Postgres and
Redis, or start them with `docker compose up -d postgres redis` (they are not
published to the host by default, so add a port mapping if you run the backend
outside Compose).

### Tests

Most of the suite runs against real services: Postgres 16 (migrations,
constraints, full-text search), Redis (session revocation, login rate limit)
and an S3-compatible server (RustFS) for the S3 storage backend. Locally these
come from testcontainers, so Docker must be running. Without Docker, those
tests skip and only the pure unit tests run.

To use existing services instead of testcontainers, set:

```
OPENCLEF_TEST_DATABASE_URL   postgresql+asyncpg://user:pass@host:5432/db
OPENCLEF_TEST_REDIS_URL      redis://host:6379/0
OPENCLEF_TEST_S3_ENDPOINT    http://host:9000
OPENCLEF_TEST_S3_ACCESS_KEY / OPENCLEF_TEST_S3_SECRET_KEY
```

CI does exactly this, running the three as job services (see `.gitlab-ci.yml`).

## Frontend (SvelteKit 2, Svelte 5)

```bash
cd frontend
npm ci
npm run dev      # http://localhost:5173, proxies /api and /health to :8000
npm run check    # svelte-kit sync + svelte-check
npm test         # Vitest
npm run build    # static SPA in build/
```

In production the FastAPI process serves the static build (copied to
`/app/static` in the image) and the API from a single origin, with an SPA
fallback route.

## Configuration

All runtime config is read from `OPENCLEF_*` environment variables via
Pydantic Settings. Defaults live in `backend/src/openclef/config.py`;
`.env.example` documents the common ones.

| Variable | Default | Purpose |
|---|---|---|
| `OPENCLEF_DATABASE_URL` | `postgresql+asyncpg://openclef:openclef@localhost:5432/openclef` | async SQLAlchemy URL |
| `OPENCLEF_REDIS_URL` | `redis://localhost:6379/0` | session revocation, login rate limit, Dramatiq broker |
| `OPENCLEF_ENV` | `dev` | `dev` / `staging` / `prod` |
| `OPENCLEF_VERSION` | `dev` | exposed by `/api/v1/version`; CI sets it |
| `OPENCLEF_AUTO_MIGRATE` | `true` | run `alembic upgrade head` from the entrypoint |
| `OPENCLEF_PEPPER` | (none) | password-hash pepper; required outside `dev` |
| `OPENCLEF_SECRET_KEY` | (none) | session-cookie signing key; required outside `dev` |
| `OPENCLEF_ADMIN_USER` / `OPENCLEF_ADMIN_PASSWORD` | (none) | optional first-run admin bootstrap; set both or neither |
| `OPENCLEF_STORAGE_BACKEND` | `local` | `local` or `s3` |
| `OPENCLEF_DATA_DIR` | `/var/lib/openclef/data` | local storage root (`/app/data` in the image) |
| `OPENCLEF_S3_BUCKET`, `_ENDPOINT`, `_REGION`, `_ACCESS_KEY`, `_SECRET_KEY`, `_PATH_STYLE` | | S3-compatible storage (Garage, MinIO, AWS, ...) |
| `OPENCLEF_THUMBNAIL_CACHE_MB` | `500` | on-disk thumbnail cache, S3 backend only |
| `OPENCLEF_MAX_UPLOAD_MB` | `100` | largest PDF accepted per upload |
| `OPENCLEF_OIDC_ISSUER`, `_CLIENT_ID`, `_CLIENT_SECRET`, `_REDIRECT_URI` | | enable "Sign in with ..." when all are set |
| `OPENCLEF_OIDC_PROVIDER_NAME` | `SSO` | label on the sign-in button |
| `OPENCLEF_OIDC_ADMIN_GROUP` | (none) | members of this `groups` claim value become admins |
| `OPENCLEF_STATIC_DIR` | `/app/static` | where FastAPI finds the frontend build |

For OIDC, register `https://<your host>/api/v1/auth/oidc/callback` as the
redirect URI and make sure the provider has the authorization-code grant
enabled. A first SSO sign-in creates a regular account; an existing password
account can link SSO from Settings.

## CI

`.gitlab-ci.yml` runs on every merge request and on `main`:

- `secret_detection`: GitLab's secret-detection template.
- `test:backend`: `ruff check` and the full `pytest` suite against Postgres,
  Redis and RustFS service containers.
- `test:frontend`: `npm run check` and Vitest.
- `docs:build`: builds the Starlight snapshot when `docs/` changes.
- `build:image`: Kaniko builds the container image, tagged by short SHA and,
  on a `vX.Y.Z` tag, by version.
