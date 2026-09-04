# Pan-African SDMX Trade Data Hub

An end-to-end official-statistics engineering portfolio: SDMX metadata, governed
trade-data ingestion, validation, harmonisation, lineage, PostgreSQL, a FastAPI
REST API, and a React Data Explorer in one deployable container.

**Live Demo:** `<PUBLIC_URL>` (pending deployment authorization)  
**API Docs:** `<PUBLIC_URL>/docs` (pending deployment authorization)  
**Source:** [GitHub](https://github.com/hagiye/Africa-sdmx-trade-hub)

> **Disclaimer:** `AFRSTAT:AFR_TRADE` and this application are independent
> portfolio demonstration artefacts and are not official African Union or
> STATAFRIC systems or standards.

## What it demonstrates

- Real SDMX structural metadata for `UNSD:IMTS`
- Bounded UN Comtrade ingestion with deterministic observation identity
- DSD- and codelist-aware source validation
- Canonical bilingual African geography
- Auditable PostgreSQL source warehouse and revision handling
- Versioned source-to-target concept and code mappings
- `AFRSTAT:AFR_TRADE(1.0)` harmonisation and target validation
- Observation-level mapping trace and lineage
- Read-only REST API, Swagger, and ReDoc
- React and TypeScript Data Explorer, metadata, validation, and lineage views
- Multi-stage, non-root Docker deployment serving UI and API from FastAPI

## Architecture

```mermaid
flowchart TD
    A[UN Comtrade] --> B[UNSD:IMTS]
    B --> C[Source Validation]
    C --> D[PostgreSQL Source Warehouse]
    D --> E[Mapping Registry]
    E --> F[AFR_TRADE]
    F --> G[Target Validation]
    G --> H[Harmonised Warehouse]
    H --> I[FastAPI]
    I --> J[React Data Explorer]
```

The React production build is copied into the Python image. FastAPI serves the
SPA at `/`, preserves direct client routes such as `/metadata`, and never turns
an unknown `/api/*` route into a frontend response.

## Public routes

- `/` — Data Explorer landing page
- `/explore` — filterable AFR_TRADE observations
- `/metadata` — DSD and codelist metadata
- `/validation` — stored validation evidence
- `/harmonization` — mappings, batches, and lineage
- `/architecture` and `/about` — design and attribution
- `/docs` and `/redoc` — interactive API documentation
- `/health` — concise liveness response
- `/api/v1/afr-trade` — read-only statistics API
- `/api/v1/afr-trade/metadata` — target metadata

## Local development

Prerequisites are Python 3.12+, Node.js 22+, Docker, and Docker Compose.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm --prefix frontend ci
Copy-Item .env.example .env
# Set local POSTGRES_* values for Compose and a local DATABASE_URL in .env.
docker compose up -d
alembic upgrade head
python -m pytest -v
npm --prefix frontend test
npm --prefix frontend run build
```

Run the two development processes:

```powershell
python -m uvicorn app.main:app --reload
npm --prefix frontend run dev
```

The Vite development proxy sends `/api`, `/health`, `/docs`, and `/redoc` to
the backend. `VITE_API_BASE_URL` is optional for development and is deliberately
empty in the production image so browser requests remain same-origin.

## Production container

Build and run the single-worker production image:

```powershell
docker build -t africa-sdmx-trade-hub .
docker run --rm -p 8000:8000 `
  -e PORT=8000 `
  -e ENVIRONMENT=production `
  -e DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require" `
  africa-sdmx-trade-hub
```

The runtime uses a non-root user, one Uvicorn worker, a small SQLAlchemy pool,
`pool_pre_ping`, and the platform-supplied `PORT`. Application startup performs
no migrations, database bootstrap, or live provider ingestion.

## Migrations and controlled demo data

Migrations are an explicit, single-operator action. Apply them before starting
the first deployment; do not run concurrent migration commands from replicas.

```powershell
$env:DATABASE_URL = "postgresql+psycopg://..."
alembic upgrade head
alembic check
python scripts/bootstrap_demo_database.py
python scripts/bootstrap_demo_database.py  # proves idempotency
```

The bootstrap refuses a database that is not at the Alembic head. It uses only
checked-in structure snapshots, canonical reference data, mappings, and three
controlled UN Comtrade response fixtures (2022–2024). It never contacts UN
Comtrade or another SDMX provider.

## Deployment

See [Production deployment](docs/deployment.md) for the free-tier guardrails,
Neon setup, the deliberate one-time migration flow, Koyeb configuration, cold
starts, security headers, and verification checklist.

After deployment, run:

```powershell
python scripts/smoke_test_deployment.py https://YOUR-REAL-DOMAIN
```

The smoke test checks the landing page, health, Swagger, AFR_TRADE data and
metadata, plus a filtered statistics query.

## Configuration

All production configuration comes from environment variables. Copy
`.env.example` only for local setup; never commit `.env`.

| Variable | Purpose |
| --- | --- |
| `ENVIRONMENT` | Set to `production` on the public service |
| `DATABASE_URL` | Hosted PostgreSQL URL; `postgres://` and `postgresql://` are normalized to psycopg v3 |
| `DATABASE_SSL_MODE` | Optional psycopg SSL mode; use `require` when the provider requires TLS |
| `SECRET_KEY` | Reserved application secret; store as a platform secret |
| `PORT` | Listener port supplied by the hosting platform |
| `CORS_ALLOWED_ORIGINS` | Optional comma-separated trusted origins; empty for same-origin production |
| `DATABASE_POOL_SIZE` | Conservative persistent connection count (default `2`) |
| `DATABASE_MAX_OVERFLOW` | Short-lived connections beyond the pool (default `1`) |

Production rejects wildcard CORS. Responses include `X-Content-Type-Options`,
`Referrer-Policy`, frame protection, and a Swagger-compatible content security
policy. Unhandled errors return a generic response; secrets and database URLs
are not logged.

## Documentation

- [AFR_TRADE model](docs/afr-trade-model.md)
- [Mapping registry](docs/afr-trade-mapping.md)
- [Harmonisation pipeline](docs/afr-trade-harmonization.md)
- [Persistence, validation, and lineage](docs/afr-trade-persistence.md)
- [Validation engine](docs/validation-engine.md)
- [Statistical warehouse](docs/statistical-warehouse.md)

## License and data terms

Application code is available under the [MIT License](LICENSE). That license
does not relicense third-party statistical data, metadata, or provider material.
UN Comtrade-derived fixtures and metadata retain their source attribution and
remain subject to the applicable provider terms. `AFRSTAT:AFR_TRADE` is an
independent demonstration artefact, not an official standard.
