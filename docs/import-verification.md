# Structure import verification

Verified on: `2026-09-02`

The PostgreSQL registry was migrated from an empty schema with `alembic upgrade
head`. The live importer was then run twice against IMF SDMX Central.

| Registry table | After first import | After second import |
|---|---:|---:|
| `sdmx_dataflow` | 1 | 1 |
| `sdmx_dsd` | 1 | 1 |
| `sdmx_concept_scheme` | 2 | 2 |
| `sdmx_concept` | 44 | 44 |
| `sdmx_codelist` | 13 | 13 |
| `sdmx_code` | 71,105 | 71,105 |
| `sdmx_dimension` | 19 | 19 |
| `sdmx_attribute` | 11 | 11 |
| `sdmx_measure` | 1 | 1 |

The first run inserted 71,197 registry records. The second run reported 17
unchanged top-level structures, zero inserts, zero updates, and zero checksum
changes. The provider returned HTTP 404 for
`/structure/dataconstraint/UNSD/all/latest`, so no constraint was imported and
the absence was reported explicitly.

The exact DSD dimension order is recorded in [trade-dsd.md](trade-dsd.md).
