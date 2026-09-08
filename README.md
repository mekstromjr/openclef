# OpenClef

> **Read-only mirror.** This project is developed on a self-hosted GitLab instance and
> mirrored to GitHub for visibility. Issues and pull requests are not accepted here;
> the mirror is overwritten on every push. Contact: see the profile of [@mekstromjr](https://github.com/mekstromjr).

Open-source, self-hosted, web-based sheet music library manager for performers.

> **Status:** Phase 1 scaffolding (deployment baseline only — no domain features yet). See [openclef-phase-1 epic](https://gitlab.meklab.net/meklab/meklab/-/blob/main/vault/Epics/openclef-phase-1.md) for the roadmap.

## What it is (eventually)

A library you can fill with PDFs of sheet music, search across by title / composer / arranger / instrumentation / tags, view in a browser at sight-reading quality, and (Phase 2) annotate, organize into setlists, and read in a performance-mode UI optimized for the music stand.

## What it is right now

A FastAPI + SvelteKit hello-world that boots cleanly against PostgreSQL + Redis and is deployable via Docker Compose. Every endpoint beyond `/health` and `/api/v1/version` is intentionally absent — the scaffolding is here so feature tickets have a known-good environment to extend.

## Quickstart — Docker Compose

```bash
git clone ssh://git@gitlab.meklab.net:2222/meklab/openclef.git
cd openclef
cp .env.example .env
docker compose up -d
```

The stack comes up healthy in about 15 seconds. The `.env` file bootstraps
a dev admin (`admin` / `password`) on first run — explicitly weak, never
use these values for anything but local development. See
[`.env.example`](.env.example) for the full set of available variables.

Sign in at `http://localhost:8000/login` with `admin` / `password`.

Then:

```bash
curl http://localhost:8000/health
# {"status":"ok","db":"connected","storage":"ok"}

curl http://localhost:8000/api/v1/version
# {"version":"dev","name":"openclef"}

open http://localhost:8000/
```

Tear down with `docker compose down` (add `-v` to wipe the database volume).

### What you get

| Service | Image | Port |
|---|---|---|
| `app` | built locally from `Dockerfile` | 8000 |
| `postgres` | `postgres:16.6-alpine` | (internal) |
| `redis` | `redis:7.4-alpine` | (internal) |

The app container runs `alembic upgrade head` on startup before exec'ing uvicorn. The Phase 1 baseline migration is empty — real schema arrives in [ticket 0135](https://gitlab.meklab.net/meklab/meklab/-/blob/main/vault/Stubs/0135-openclef-data-model.md).

## Quickstart — Kubernetes (Helm)

Manifests live in `meklab-k8s/apps/openclef/` and are reconciled by Flux. The chart skeleton is **not yet shipped** — it lands in a follow-up commit on this same ticket. For now, Compose is the only supported deployment path.

## Local development

### Backend (Python 3.12 + uv)

```bash
cd backend
uv venv
uv pip install -e ".[dev]"
.venv/bin/pytest      # 3 smoke tests, all passing
.venv/bin/uvicorn openclef.main:app --reload --port 8000
```

Set `OPENCLEF_DATABASE_URL` and `OPENCLEF_REDIS_URL` to point at your local Postgres + Redis (or just bring them up via `docker compose up postgres redis`).

### Frontend (Node 20 + SvelteKit 5)

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173, proxies /api → :8000
npm run build    # writes static SPA to build/
npm run check    # svelte-check + tsc
```

The Vite dev server proxies `/api` and `/health` to `localhost:8000` so the SPA can fetch the FastAPI backend without CORS plumbing. In production the same FastAPI process serves both the static build (`build/` → `/app/static`) and the API on a single origin.

## Configuration

All runtime config is read from `OPENCLEF_*` environment variables via Pydantic Settings. Defaults in [`backend/src/openclef/config.py`](backend/src/openclef/config.py).

| Variable | Default | Purpose |
|---|---|---|
| `OPENCLEF_DATABASE_URL` | `postgresql+asyncpg://openclef:openclef@localhost:5432/openclef` | async SQLAlchemy URL |
| `OPENCLEF_REDIS_URL` | `redis://localhost:6379/0` | Dramatiq broker (no jobs registered yet) |
| `OPENCLEF_VERSION` | `dev` | exposed by `/api/v1/version`; CI sets to short SHA |
| `OPENCLEF_ENV` | `dev` | `dev` / `staging` / `prod` |
| `OPENCLEF_AUTO_MIGRATE` | `true` | run `alembic upgrade head` from entrypoint |
| `OPENCLEF_DATA_DIR` | `/var/lib/openclef/data` | local storage backend root (Phase 1 stub) |
| `OPENCLEF_STORAGE_BACKEND` | `local` | `local` or `s3` (S3 lands in ticket 0137) |
| `OPENCLEF_STATIC_DIR` | `/app/static` | where FastAPI looks for the SvelteKit build |

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12 · FastAPI 0.115 · SQLAlchemy 2 async · Alembic · Pydantic 2 · structlog · Dramatiq+Redis |
| Frontend | SvelteKit 5 · Vite 6 · Tailwind 4 · TypeScript |
| PDF (future) | pdf.js (viewing) · pypdfium2 (server-side thumbs) · pypdf (metadata) |
| Storage | swappable Local FS / S3-compatible (Garage, MinIO, AWS) |
| Auth | Argon2id sessions; optional OIDC via authlib |
| Deploy | Docker Compose · Helm chart for K3s |

## License

Apache 2.0 — see [LICENSE](LICENSE) (file landing alongside this README).

## Contributing

OpenClef is currently developed inside the [meklab homelab project](https://gitlab.meklab.net/meklab). External contributions aren't actively solicited yet, but the design intent is to be friendly to other self-hosters once Phase 1 is complete.
