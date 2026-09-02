# Pan-African SDMX Trade Data Hub

An independent portfolio project demonstrating SDMX-based ingestion, harmonisation, validation and dissemination of African international trade statistics.

## Disclaimer

This is an independent portfolio demonstration project and is not an official African Union or STATAFRIC platform.

## Current architecture

```text
FastAPI
   ↓
SQLAlchemy
   ↓
PostgreSQL
```

This phase manages structural metadata only. It does not ingest trade
observations.

## SDMX Structure Discovery

The project discovers and imports four related SDMX structure types:

- A **Dataflow** identifies a published dataset and references its structure.
- A **DSD** defines the ordered dimensions, measures, and attributes of data.
- A **Concept Scheme** defines the concepts used by those components.
- A **Codelist** defines allowed codes and their multilingual labels.

Live discovery on 2026-09-02 selected the public IMF SDMX Central registry at
`https://sdmxcentral.imf.org/sdmx/v2/`. The trade dataflow is
`UNSD:IMTS_A(1.0)` and it references `UNSD:IMTS(1.2)`, International
Merchandise Trade Statistics. The agency identifier is preserved as `UNSD`;
this project does not claim that the structure is owned by IMF.

```text
SDMX Provider
    |
Dataflow
    |
DSD
  /   \
Concepts  Codelists
    \     /
PostgreSQL Metadata Registry
    |
FastAPI Metadata API
```

Raw response SHA-256 values are logged for traceability. Change detection uses
a canonical SHA-256 of the `<Structures>` content so volatile SDMX message IDs
and preparation timestamps do not trigger false updates.

## Development setup

Run these commands from PowerShell on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Replace the placeholder passwords in .env before starting services.
docker compose up -d
alembic upgrade head
python -m uvicorn app.main:app --reload
```

Run the automated tests separately:

```powershell
python -m pytest -v
```

## Structure commands

```powershell
python scripts/discover_provider.py
python scripts/discover_dataflows.py
python scripts/inspect_trade_dsd.py
python scripts/import_structures.py
python scripts/show_metadata_registry.py
pytest -v
```

Live integration tests are explicit and are excluded from the deterministic
default suite:

```powershell
pytest -m integration -v
```

## API

- `/` — service metadata
- `/health` — service health status
- `/docs` — Swagger UI
- `/redoc` — ReDoc documentation
- `/api/v1/dataflows`
- `/api/v1/dataflows/{agency}/{dataflow_id}/{version}`
- `/api/v1/dsd/{agency}/{dsd_id}/{version}`
- `/api/v1/dsd/{agency}/{dsd_id}/{version}/dimensions`
- `/api/v1/codelists`
- `/api/v1/codelists/{agency}/{codelist_id}/{version}`
- `/api/v1/codelists/{agency}/{codelist_id}/{version}/codes`

Independent portfolio demonstration project. Not an official African Union or STATAFRIC platform.
