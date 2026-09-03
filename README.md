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

The current implementation combines the SDMX metadata registry with canonical
geography, bounded UN Comtrade ingestion, deterministic observation identity,
revision handling, rule-based validation, and a governed AFR_TRADE target
warehouse. Validation and harmonization rejection evidence is persisted.

```text
UN Comtrade
    |
UNSD source warehouse
    |
source validation
    |
mapping registry
    |
AFR_TRADE transformation
    |
target validation
    |
AFR_TRADE harmonised warehouse
    |
statistical REST API
```

See `docs/validation-engine.md` for the distinction between SDMX structural
rules and application scope such as AU-reporter eligibility.

The independent canonical target design is documented in
`docs/afr-trade-model.md`. `AFRSTAT:AFR_TRADE(1.0)` is a portfolio demonstration
structure, not an official African Union or STATAFRIC artefact.

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
python scripts/test_database.py
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

## AFR_TRADE mapping registry

Step 26B's version-aware, metadata-only mapping registry is documented in
[`docs/afr-trade-mapping.md`](docs/afr-trade-mapping.md). Load and inspect it
after both source and target structures are present:

```powershell
python scripts/load_afr_trade_mappings.py
python scripts/show_afr_trade_mappings.py
python scripts/report_mapping_coverage.py
```

## AFR_TRADE harmonization

The in-memory two-stage validation and transformation workflow is documented
in [`docs/afr-trade-harmonization.md`](docs/afr-trade-harmonization.md).

```powershell
python scripts/transform_trade_fixtures.py
python scripts/show_harmonization_trace.py
```

## AFR_TRADE persistence and API

The target-valid-only persistence lifecycle, mapping-version policy, lineage,
quality reporting, and read-only statistical REST API are documented in
[`docs/afr-trade-persistence.md`](docs/afr-trade-persistence.md).

```powershell
python scripts/harmonize_trade_data.py
python scripts/show_afr_trade_warehouse.py
python scripts/report_harmonization_quality.py
python scripts/show_observation_lineage.py
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
- `/api/v1/afr-trade`
- `/api/v1/afr-trade/{observation_id}`
- `/api/v1/afr-trade/metadata`

## Data Explorer

The recruiter-facing React and TypeScript application in `frontend/` presents
the project as a restrained statistical dissemination portal. It includes:

- Home — live statistical coverage and pipeline summary
- Data Explorer — explicit filters, labelled table, time-series chart, filtered
  CSV export, and exact API-query viewer
- Metadata — target components and bilingual codelists
- Validation — stored validation summaries, rules, and findings
- Harmonisation — batch counts, mapping matrix, rejection evidence, and lineage
- Architecture, API, and About — system context, access points, attribution, and
  the non-official disclaimer

Run the backend and frontend separately during development:

```powershell
# Terminal 1 — backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

`VITE_API_BASE_URL` may point to an explicit backend origin. When unset, the
Vite development proxy and future same-origin deployments use relative API
URLs. Production static hosting is intentionally not configured in Step 27.

Verified application screenshots belong in `docs/screenshots/`; the repository
does not include fabricated placeholders.

Independent portfolio demonstration project. Not an official African Union or STATAFRIC platform.
