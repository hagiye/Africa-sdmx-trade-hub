# Trade observation query discovery

Verified on: `2026-09-02`

This checkpoint discovers and probes the query contract only. It does not
parse observations into warehouse models and does not write observations to
PostgreSQL.

## Result and provider boundary

The real observation provider is **UN Comtrade**. A deliberately narrow public
preview query returns one Kenya annual import observation with HTTP `200`.

The SDMX structures and observations are served by different systems:

- IMF SDMX Central stores the selected Dataflow and DSD. Its entry point is
  `https://sdmxcentral.imf.org/sdmx/v2/`; it implements SDMX REST v2 and returns
  SDMX 3.0 structure messages.
- UN Comtrade serves the actual trade observations at
  `https://comtradeapi.un.org/public/v1/preview`. This is Comtrade REST API v1,
  not an SDMX REST observation endpoint.

The registry's `/data` resource returns HTTP `501`, and UN Comtrade's retired
`getSdmxV1.aspx` service redirects to an error page. Therefore the application
must not pretend that an SDMX positional key can be sent directly to the live
observation endpoint. The stored SDMX metadata is used as the semantic contract
and its supported dimensions are translated to Comtrade's named parameters.

## Stored structure identities

- Dataflow: `UNSD:IMTS_A(1.0)` — IMTS Annual
- DSD: `UNSD:IMTS(1.2)` — International Merchandise Trade Statistics

The script loads both records and the component order from the PostgreSQL
metadata registry. It also resolves the sample SDMX codes by their imported
English codelist labels; no SDMX code is guessed.

## Exact DSD dimension order

| Position | Dimension | SDMX key component? |
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
| 19 | `TIME_PERIOD` | no; it is the time dimension |

An SDMX REST v2 positional key contains the first 18 components in exactly
that order, separated by dots. `*` means any value for one component. Multiple
values within one component use `+`; multiple complete keys use commas.

The codelist-derived sample key is:

```text
A.KE.M.HS17_TOTAL.*.*.*.*.W0.*.W0.*.*.*.*.*.*.*
```

It fixes annual frequency, Kenya, total imports, all HS 2017 commodities, and
World for both counterpart dimensions. Remaining components are wildcarded.
This key documents the stored DSD contract; it is not sent to Comtrade v1.

## Mapping the DSD to the real provider

UN Comtrade v1 uses three path values followed by named query parameters:

```text
{endpoint}/{typeCode}/{freqCode}/{classificationCode}?{parameters}
```

For the sample, the provider path key is `C/A/HS`:

- `C` selects merchandise (commodity) trade.
- `A` is resolved from `SDMX:CL_FREQ(2.0)` by the label `Annual`.
- `HS` asks Comtrade for the reporter's original Harmonized System edition.

The supported dimension translation is:

| Stored DSD dimension | Comtrade v1 location | Sample resolution |
|---|---|---|
| `FREQ` | path `freqCode` | `A`, from the stored codelist |
| `REF_AREA` | `reporterCode` | stored `KE`; official `Reporters.json` resolves it to M49 `404` |
| `TRADE_FLOW` | `flowCode` | `M`, from stored label `Total Imports` |
| `COMMODITY_1` | path `classificationCode` plus `cmdCode` | stored `HS17_TOTAL`; provider route `HS`, command `TOTAL` |
| `COUNTERPART_AREA_1` | `partnerCode` | stored `W0`; official `partnerAreas.json` resolves World to `0` |
| `COUNTERPART_AREA_2` | `partner2Code` | World, provider code `0` |
| `TIME_PERIOD` | `period` | `2020` |

Other DSD dimensions are not directly expressible by the classic preview
query. `breakdownMode=classic` asks Comtrade for the classic aggregate, and
the response confirms total customs and transport values. The returned record
also confirms classification `H5`, Comtrade's identifier for HS 2017, matching
the stored `HS17_TOTAL` codelist code.

## Exact bounded query

The data endpoint template is:

```text
https://comtradeapi.un.org/public/v1/preview/{typeCode}/{freqCode}/{classificationCode}
```

The verified request is:

```text
https://comtradeapi.un.org/public/v1/preview/C/A/HS?period=2020&reporterCode=404&flowCode=M&partnerCode=0&partner2Code=0&cmdCode=TOTAL&maxRecords=1&breakdownMode=classic&includeDesc=true&format=JSON
```

`maxRecords=1`, the fully specified aggregate, and the client's 64 KiB response
cap prevent a large transfer. The script rejects the response unless it has
exactly one matching record with a non-null `primaryValue`.

## Date parameters

Standard SDMX REST data queries use inclusive `startPeriod` and `endPeriod`
parameters. The live Comtrade v1 endpoint does **not** use those names; it uses
`period` (`YYYY` for annual data and `YYYYMM` for monthly data). Thus this
checkpoint's bounds:

```text
startPeriod=2020&endPeriod=2020
```

translate exactly to:

```text
period=2020
```

The discovery script intentionally requires equal start and end periods. A
future ingestion step must explicitly implement range expansion rather than
silently treating Comtrade's parameter as an SDMX date range.

## Response formats and limits

- The sample requests and parses JSON with `format=JSON` and returns HTTP `200`.
- UN Comtrade's official Python client documents JSON and CSV output for data
  queries. The help centre also documents text output for supported download
  endpoints. JSON is used here because it permits strict validation without
  saving a response file.
- The unauthenticated public preview endpoint is capped at 500 records. The
  script requests one.
- Authenticated data endpoints require a subscription key and support larger
  limits; the official client documents a 250,000-record cap for synchronous
  final-data calls. This checkpoint uses neither endpoint nor credentials.
- The provider publishes no numeric unauthenticated rate limit. HTTP `429` can
  occur when requests are made too rapidly.
- The prior structure discovery found no published UNSD content constraint in
  IMF SDMX Central (HTTP `404`). A valid codelist code is therefore not proof
  that every combination has observations; this script proves the sample by
  checking a real returned record.

## Reproduce

With PostgreSQL running and Checkpoints 1–18 imported:

```powershell
python scripts/discover_trade_query.py
```

The script performs read-only metadata queries plus one one-record observation
probe. It does not modify the statistical warehouse.

## Sources

- [UN Comtrade API documentation](https://uncomtrade.org/docs/un-comtrade-api/)
- [UN Comtrade country-code references](https://uncomtrade.org/docs/country-codes/)
- [Official UN Comtrade Python client](https://github.com/uncomtrade/comtradeapicall)
- [SDMX-IMTS structures](https://comtrade.un.org/sdmx/)
- [SDMX REST data-query specification](https://github.com/sdmx-twg/sdmx-rest/blob/master/doc/data.md)
