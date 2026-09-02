# Trade observation query discovery

Verified on: `2026-09-02`

This checkpoint is discovery only. No observations are parsed or written to
PostgreSQL.

## Result

The selected structural provider, **IMF SDMX Central**, does not currently
expose a working data resource for this Dataflow. Its API-v2 candidate data
endpoint returns HTTP `501` with the message `data resource not supported for
API version 2`. The provider's legacy SDMX REST endpoint was checked as a
fallback and also returns HTTP `501`, with `Data Queries are not implemented`.

Therefore, the Dataflow and DSD are usable structural metadata, but they are
not evidence of a queryable observation feed. A warehouse ingestion step must
not be built against this registry until a real observation provider is
identified.

## Stored structure identities

- Provider: IMF SDMX Central
- Structure API entry point: `https://sdmxcentral.imf.org/sdmx/v2/`
- SDMX REST API version: `2.0.0`
- Structure message version: SDMX `3.0`
- Dataflow: `UNSD:IMTS_A(1.0)` — IMTS Annual
- DSD: `UNSD:IMTS(1.2)` — International Merchandise Trade Statistics

The script reads these identities and the component order from the local
metadata registry. It does not duplicate the DSD as an independent source of
truth.

## Exact dimension order

| Position | Dimension | Key component? |
|---:|---|---|
| 1 | `FREQ` | yes |
| 2 | `REF_AREA` | yes |
| 3 | `TRADE_FLOW` | yes |
| 4 | `COMMODITY_1` | yes |
| 5 | `COMMODITY_1_CONF` | yes |
| 6 | `COMMODITY_2` | yes |
| 7 | `COMMODITY_2_CONF` | yes |
| 8 | `COMMODITY_CUSTOM_BREAKDOWN` | yes |
| 9 | `COUNTERPART_AREA_1` | yes |
| 10 | `COUNTERPART_AREA_1_CONF` | yes |
| 11 | `COUNTERPART_AREA_2` | yes |
| 12 | `COUNTERPART_AREA_2_CONF` | yes |
| 13 | `TRANSPORT_MODE_BORDER` | yes |
| 14 | `TRANSPORT_MODE_BORDER_CONF` | yes |
| 15 | `CUSTOMS_PROC` | yes |
| 16 | `ACTIVITY` | yes |
| 17 | `TRANSFORMATION` | yes |
| 18 | `MEASURE` | yes |
| 19 | `TIME_PERIOD` | no; supplied with date parameters |

The positional key contains the first 18 dimensions in exactly this order.
`TIME_PERIOD` is filtered separately.

## Query construction

The SDMX REST v2 candidate path is:

```text
{entry-point}/data/dataflow/{agency}/{dataflow-id}/{version}/{key}
```

For this Dataflow:

```text
https://sdmxcentral.imf.org/sdmx/v2/data/dataflow/UNSD/IMTS_A/1.0/{key}
```

Key components are separated by dots. `*` is the API-v2 wildcard for any
value in one dimension. Multiple complete keys would be separated by commas.
The sample fixes only three codes and leaves every other key dimension
wildcarded:

```text
A.KE.M.*.*.*.*.*.*.*.*.*.*.*.*.*.*.*
```

These codes are resolved by English label from the imported codelists at run
time; they are not guessed:

| Dimension | Stored codelist | Label selected | Code resolved |
|---|---|---|---|
| `FREQ` | `SDMX:CL_FREQ(2.0)` | Annual | `A` |
| `REF_AREA` | `UNSD:CL_AREA(1.0)` | Kenya | `KE` |
| `TRADE_FLOW` | `UNSD:CL_TRADE_FLOW(1.0)` | Total Imports | `M` |

The complete bounded probe is:

```text
https://sdmxcentral.imf.org/sdmx/v2/data/dataflow/UNSD/IMTS_A/1.0/A.KE.M.*.*.*.*.*.*.*.*.*.*.*.*.*.*.*?startPeriod=2023&endPeriod=2023&firstNObservations=1&max=1
```

`startPeriod` and `endPeriod` use valid SDMX time-period strings and are
inclusive bounds in the Fusion Registry data-query implementation. The
provider implementation documents these parameters for both its legacy and
API-v2 entry points. The SDMX REST v2 standard also offers component-filter
syntax such as `c[TIME_PERIOD]=ge:2023+le:2023`; this probe retains
`startPeriod` and `endPeriod` because those are the provider-documented
parameters required by this checkpoint.

## Response formats

The probe requests SDMX-CSV 2.0 with:

```http
Accept: application/vnd.sdmx.data+csv;version=2.0.0
```

The Fusion Registry implementation advertises SDMX-JSON, SDMX-CSV, SDMX-EDI,
SDMX-ML Generic Data, and SDMX-ML Structure Specific Data. The current IMF
SDMX Central deployment cannot demonstrate any successful data format because
the data resource is disabled. Its `501` response is an SDMX-ML 2.1 error
document returned as `application/xml;charset=UTF-8`.

## Constraints and limits

- The earlier content-constraint discovery request for UNSD returned HTTP
  `404`; no content constraint was imported. Consequently, codelist validity
  can be proven for each selected code, but availability of this exact code
  combination cannot be claimed.
- The API-v2 availability resource returns HTTP `501` and says that the
  resource is unsupported.
- No numeric provider-side series, observation, payload, or rate limit is
  disclosed in the responses or provider guide.
- To prevent a large transfer if the resource is enabled later, the script
  sends `firstNObservations=1` and the Fusion `max=1` pagination extension,
  streams the response, and reads at most 64 KiB.

## Reproduce

With PostgreSQL running and the structural registry already imported:

```powershell
python scripts/discover_trade_query.py
```

The expected discovery status as of the verification date is HTTP `501`, not
HTTP `200`. That status is a provider capability result, not a script failure.

## Sources

- [IMF SDMX Central Web Services Guide](https://dsbb.imf.org/content/pdfs/IMFSDMXCentralWebServicesGuide.pdf)
- [Fusion Registry data-query service](https://wiki.sdmxcloud.org/Data_Query_Web_Service)
- [SDMX REST data-query specification](https://github.com/sdmx-twg/sdmx-rest/blob/master/doc/data.md)
