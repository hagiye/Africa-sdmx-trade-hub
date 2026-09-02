# SDMX provider discovery

Checked on: `2026-09-02`

| Provider | Endpoint | Purpose | Result | SDMX version | Authentication | Notes |
|---|---|---|---|---|---|---|
| IMF SDMX Central | `https://sdmxcentral.imf.org/sdmx/v2/` | Dataflows, DSDs, concept schemes, codelists, constraints, and SDMX data | HTTP 200 for the selected UNSD structures | 3.0 response; 2.1 and other formats are also offered | None for public structures | This is the structural registry used by the project. Structure ownership remains with each response's agency. |
| IMF Data API | `https://data.imf.org/en/Resource-Pages/IMF-API` | Current IMF statistical data API documentation | HTTP 403 for direct scripted access from this environment | Official documentation states 2.1 and 3.0 | Portal sign-in is required to open Swagger | The official page is indexed, but it is not used for the UNSD structure registry in this phase. |
| IMF DataMapper API | `https://www.imf.org/external/datamapper/api/v1/` | DataMapper time series | HTTP 403 from this environment | Not SDMX | Access is edge-restricted here | Not suitable for structure discovery. |

## Selected structure graph

The live registry returned `UNSD:IMTS_A(1.0)`, named **IMTS Annual**, and that
dataflow explicitly references `UNSD:IMTS(1.2)`, named **International
Merchandise Trade Statistics**. The selected DSD is owned by `UNSD`; hosting it
in IMF SDMX Central does not make it an IMF-owned structure.

The importer follows references in the DSD instead of guessing codelist or
concept-scheme identifiers. A query for UNSD data constraints is also made. A
missing constraint endpoint is recorded explicitly rather than treated as an
empty successful response.

The probe is repeatable with:

```powershell
python scripts/discover_provider.py
```
