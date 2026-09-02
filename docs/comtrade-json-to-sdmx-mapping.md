# UN Comtrade JSON to SDMX-IMTS Mapping

- Provider: **UN Comtrade / UNSD**
- Dataflow: `UNSD:IMTS_A(1.0)`
- DSD: `UNSD:IMTS(1.2)`
- Evidence: the controlled real Tunisia–World annual import fixtures for 2022, 2023, and 2024

This document maps the simplified UN Comtrade JSON response to the imported
SDMX semantic contract. It does not claim that the Comtrade v1 JSON endpoint is
an SDMX data endpoint, and it does not define ingestion or normalization logic.

## Envelope and statistical content

The top-level JSON object is an API envelope:

| Envelope field | Observed value | Classification |
|---|---|---|
| `count` | `1` | Envelope record count |
| `data` | array with one object | Statistical observation container |
| `elapsedTime` | e.g. `"0.05 secs"` | Volatile envelope timing metadata |
| `error` | `""` | Envelope error state |

Every complete object inside `data` is statistical record content. Envelope
fields are not part of an observation. In particular, `elapsedTime` must never
be used as evidence that statistical content changed.

`raw_response_checksum` hashes the complete canonical JSON response, including
the envelope. `statistical_content_checksum` hashes the complete records inside
`data`, preserving every record field but excluding the top-level envelope. Both
use deterministic JSON key ordering; the statistical checksum also treats the
top-level record array as order-independent. Consequently, an `elapsedTime`
change changes the raw checksum but not the statistical-content checksum; a
change to `primaryValue` or any other record field changes the statistical
checksum.

## Cross-year record structure

All three fixtures contain one record and the same 47 field names. No fields are
missing, and the records contain no empty strings, nested objects, or nested
arrays. The only Python type variation is `netWgt`: `float` (`0.0`) in 2022 and
2023, then `NoneType` (`null`) in 2024. `fobvalue` is `null` in all three years.
The values of `isNetWgtEstimated` and `legacyEstimationFlag` also change in 2024,
but their JSON types do not.

| Field | 2022 | 2023 | 2024 | Types | Nullable |
|---|---:|---:|---:|---|---|
| `fobvalue` | null | null | null | `NoneType` | yes |
| `netWgt` | 0.0 | 0.0 | null | `float`, `NoneType` | yes |
| `isNetWgtEstimated` | true | true | false | `bool` | no |
| `legacyEstimationFlag` | 4 | 4 | 0 | `int` | no |
| `period` | "2022" | "2023" | "2024" | `str` | no |
| `primaryValue` | 26672667450.171 | 25930493874.99 | 26065070572.389 | `float` | no |

Other data values also vary as expected (for example `cifvalue`, `refYear`, and
`refPeriodId`), but their field presence and JSON types remain stable. The
complete machine-readable presence, type, example, and nullability inventory is
in `data/discovery/comtrade_trade_record_fields.json`.

## Field mapping

`DIRECT` means the field directly expresses the named SDMX concept. `DERIVED`
means translation, combination, or reshaping is required. `UNKNOWN` is used when
the fixtures and imported DSD do not establish a safe relationship. Confidence
describes the mapping evidence, not data quality.

| JSON Field | Example Value | Meaning | SDMX Concept | Relationship | Confidence | Notes |
|---|---|---|---|---|---|---|
| `aggrLevel` | `0` | Commodity aggregation level | — | UNKNOWN | UNKNOWN | No matching DSD concept established. |
| `altQty` | `0.0` | Alternative quantity | `OBS_VALUE` | DERIVED | HIGH | Requires a measure and unit when reshaped. |
| `altQtyUnitAbbr` | `"N/A"` | Alternative quantity unit label | `UNIT_MEASURE` | DERIVED | HIGH | Provider label, not an SDMX code. |
| `altQtyUnitCode` | `-1` | Alternative quantity unit code | `UNIT_MEASURE` | DERIVED | HIGH | Provider-to-SDMX code translation required. |
| `cifvalue` | `26672667450.171` | CIF value | `OBS_VALUE` | DERIVED | HIGH | Value column; explicit `MEASURE` code absent. |
| `classificationCode` | `"S4"` | SITC Rev.4 classification | `COMMODITY_1` | DERIVED | CONFIRMED | Combine with `cmdCode`. |
| `classificationSearchCode` | `"S4"` | Search classification | `COMMODITY_1` | DERIVED | HIGH | Provider search metadata. |
| `cmdCode` | `"TOTAL"` | Commodity code | `COMMODITY_1` | DERIVED | CONFIRMED | `S4` + `TOTAL` resolves to stored `SITC4_TOTAL`. |
| `cmdDesc` | `"All Commodities"` | Commodity label | `COMMODITY_1` | DERIVED | HIGH | Label, not code. |
| `customsCode` | `"C00"` | Customs procedure code | `CUSTOMS_PROC` | DERIVED | HIGH | Verify/translate provider code against DSD codelist. |
| `customsDesc` | `"TOTAL CPC"` | Customs procedure label | `CUSTOMS_PROC` | DERIVED | HIGH | Label for `customsCode`. |
| `flowCode` | `"M"` | Import flow code | `TRADE_FLOW` | DIRECT | CONFIRMED | Selected stored DSD code. |
| `flowDesc` | `"Import"` | Import flow label | `TRADE_FLOW` | DIRECT | HIGH | Provider label. |
| `fobvalue` | `null` | FOB value | `OBS_VALUE` | DERIVED | HIGH | Value column; null in every fixture. |
| `freqCode` | `"A"` | Annual frequency | `FREQ` | DIRECT | CONFIRMED | Selected stored DSD code. |
| `grossWgt` | `0.0` | Gross weight | `OBS_VALUE` | DERIVED | HIGH | Value column; explicit `MEASURE` code absent. |
| `isAggregate` | `true` | Aggregate record indicator | — | UNKNOWN | UNKNOWN | Provider metadata. |
| `isAltQtyEstimated` | `false` | Alternative quantity estimated | `OBS_STATUS` | UNKNOWN | UNKNOWN | No SDMX status-code equivalence established. |
| `isGrossWgtEstimated` | `false` | Gross weight estimated | `OBS_STATUS` | UNKNOWN | UNKNOWN | No SDMX status-code equivalence established. |
| `isLeaf` | `false` | Commodity hierarchy leaf | — | UNKNOWN | UNKNOWN | Provider hierarchy metadata. |
| `isNetWgtEstimated` | `true` | Net weight estimated | `OBS_STATUS` | UNKNOWN | UNKNOWN | No SDMX status-code equivalence established. |
| `isOriginalClassification` | `false` | Original classification indicator | — | UNKNOWN | UNKNOWN | Provider classification metadata. |
| `isQtyEstimated` | `false` | Quantity estimated | `OBS_STATUS` | UNKNOWN | UNKNOWN | No SDMX status-code equivalence established. |
| `isReported` | `false` | Reported-versus-derived indicator | `OBS_STATUS` | UNKNOWN | UNKNOWN | No SDMX status-code equivalence established. |
| `legacyEstimationFlag` | `4` | Legacy estimation flag | `OBS_STATUS` | UNKNOWN | UNKNOWN | Semantics not proven equivalent to `OBS_STATUS`. |
| `mosCode` | `"0"` | Mode-of-supply code | — | UNKNOWN | UNKNOWN | Meaning here is not established. |
| `motCode` | `0` | Mode-of-transport code | `TRANSPORT_MODE_BORDER` | DERIVED | HIGH | Provider code translation/verification required. |
| `motDesc` | `"TOTAL MOT"` | Mode-of-transport label | `TRANSPORT_MODE_BORDER` | DERIVED | HIGH | Label for `motCode`. |
| `netWgt` | `0.0` | Net weight | `OBS_VALUE` | DERIVED | HIGH | Null in 2024; explicit `MEASURE` code absent. |
| `partner2Code` | `0` | Second counterpart provider code | `COUNTERPART_AREA_2` | DERIVED | CONFIRMED | Provider `0` translates to stored aggregate `W0`. |
| `partner2Desc` | `"World"` | Second counterpart label | `COUNTERPART_AREA_2` | DERIVED | HIGH | Aggregate area, not country. |
| `partner2ISO` | `"W00"` | Second counterpart provider notation | `COUNTERPART_AREA_2` | DERIVED | HIGH | Stored SDMX code is `W0`. |
| `partnerCode` | `0` | First counterpart provider code | `COUNTERPART_AREA_1` | DERIVED | CONFIRMED | Provider `0` translates to stored aggregate `W0`. |
| `partnerDesc` | `"World"` | First counterpart label | `COUNTERPART_AREA_1` | DERIVED | HIGH | Aggregate area, not country. |
| `partnerISO` | `"W00"` | First counterpart provider notation | `COUNTERPART_AREA_1` | DERIVED | HIGH | Stored SDMX code is `W0`. |
| `period` | `"2022"` | Observation period | `TIME_PERIOD` | DIRECT | CONFIRMED | Annual `YYYY`. |
| `primaryValue` | `26672667450.171` | Provider-selected primary value | `OBS_VALUE` | DIRECT | HIGH | Observation value, never `MEASURE`. |
| `qty` | `0.0` | Quantity | `OBS_VALUE` | DERIVED | HIGH | Value column requiring measure and unit semantics. |
| `qtyUnitAbbr` | `"N/A"` | Quantity unit label | `UNIT_MEASURE` | DERIVED | HIGH | Provider label. |
| `qtyUnitCode` | `-1` | Quantity unit code | `UNIT_MEASURE` | DERIVED | HIGH | Provider-to-SDMX translation required. |
| `refMonth` | `52` | Annual reference-month marker | `TIME_PERIOD` | DERIVED | MEDIUM | `period` is the direct field. |
| `refPeriodId` | `20220101` | Provider period identifier | `TIME_PERIOD` | DERIVED | HIGH | Annual year can be derived. |
| `refYear` | `2022` | Reference year | `TIME_PERIOD` | DERIVED | HIGH | Numeric form of annual period. |
| `reporterCode` | `788` | Reporter M49 provider code | `REF_AREA` | DERIVED | CONFIRMED | Official translation maps `788` to stored `TN`. |
| `reporterDesc` | `"Tunisia"` | Reporter label | `REF_AREA` | DERIVED | HIGH | Label, not SDMX code. |
| `reporterISO` | `"TUN"` | Reporter ISO alpha-3 | `REF_AREA` | DERIVED | HIGH | Stored SDMX code is `TN`. |
| `typeCode` | `"C"` | Comtrade commodity-trade API type | — | UNKNOWN | UNKNOWN | No DSD dimension mapping established. |

## Measure versus observation value

The imported DSD defines `MEASURE` as dimension 18 and separately defines
`OBS_VALUE` as its only measure component. These roles are not interchangeable:

- `MEASURE` identifies *which statistic* an SDMX observation represents.
- `OBS_VALUE` carries the numeric value for that selected statistic.

The simplified Comtrade record does not expose a dedicated `MEASURE` field or
an SDMX measure code. Instead, it returns several named numeric columns:
`primaryValue`, `qty`, `altQty`, `netWgt`, `grossWgt`, `cifvalue`, and
`fobvalue`. Converting those columns into SDMX observations would require a
future, evidenced mapping from each column to a `MEASURE` code and its unit.
That mapping is not invented here.

For these three import records, `primaryValue` exactly equals `cifvalue` and
`fobvalue` is null. This supports interpreting `primaryValue` as Comtrade's
selected primary observation value—CIF value in this narrow sample—not as the
`MEASURE` dimension and not as a universal synonym for CIF value. The DSD target
for its number is `OBS_VALUE` with HIGH, not CONFIRMED, confidence because the
required measure/unit reshaping has not yet been established.

No standalone `customsValue` field is present.

## Commodity representation

The record directly exposes classification metadata (`classificationCode`,
`classificationSearchCode`), commodity code/description (`cmdCode`, `cmdDesc`),
and aggregation metadata (`aggrLevel`, `isAggregate`, `isLeaf`, and
`isOriginalClassification`). For this query, `S4` plus `TOTAL` corresponds to
the selected stored `COMMODITY_1` code `SITC4_TOTAL`; this is a derived mapping
because no single JSON field contains the SDMX code.

No record field exposes `COMMODITY_1_CONF`, `COMMODITY_2`,
`COMMODITY_2_CONF`, or `COMMODITY_CUSTOM_BREAKDOWN`. Likewise, no custom
commodity code/description or commodity confidentiality indicator is present.
`customsCode`/`customsDesc` describe customs procedure and must not be mistaken
for custom commodity breakdown.

## Counterpart representation

The first counterpart is exposed as `partnerCode`, `partnerDesc`, and
`partnerISO`; the second uses `partner2Code`, `partner2Desc`, and `partner2ISO`.
Both map derivationally to their corresponding SDMX counterpart area because
Comtrade provider code `0`/notation `W00` translates to stored SDMX code `W0`.

In this fixture, both counterpart values mean **World**, an aggregate area.
World is explicitly classified as `AGGREGATE`, never as a country. The JSON
does not expose either counterpart confidentiality dimension. The aggregate
interpretation is compatible with the DSD counterpart type attributes, but the
records do not supply a dedicated type field, so no direct field mapping to
`COUNTERPART_AREA_1_TYPE` or `COUNTERPART_AREA_2_TYPE` is claimed.

## DSD dimension coverage

| DSD dimension | JSON evidence | Relationship |
|---|---|---|
| `FREQ` | `freqCode` | DIRECT |
| `REF_AREA` | `reporterCode`, label and ISO metadata | DERIVED |
| `TRADE_FLOW` | `flowCode` | DIRECT |
| `COMMODITY_1` | classification plus commodity fields | DERIVED |
| `COMMODITY_1_CONF` | no dedicated field | NOT EXPOSED |
| `COMMODITY_2` | no dedicated field | NOT EXPOSED |
| `COMMODITY_2_CONF` | no dedicated field | NOT EXPOSED |
| `COMMODITY_CUSTOM_BREAKDOWN` | no dedicated field | NOT EXPOSED |
| `COUNTERPART_AREA_1` | first partner fields | DERIVED |
| `COUNTERPART_AREA_1_CONF` | no dedicated field | NOT EXPOSED |
| `COUNTERPART_AREA_2` | second partner fields | DERIVED |
| `COUNTERPART_AREA_2_CONF` | no dedicated field | NOT EXPOSED |
| `TRANSPORT_MODE_BORDER` | `motCode`, `motDesc` | DERIVED |
| `TRANSPORT_MODE_BORDER_CONF` | no dedicated field | NOT EXPOSED |
| `CUSTOMS_PROC` | `customsCode`, `customsDesc` | DERIVED |
| `ACTIVITY` | no dedicated field | NOT EXPOSED |
| `TRANSFORMATION` | no dedicated field | NOT EXPOSED |
| `MEASURE` | named value columns but no measure code | NOT EXPOSED |
| `TIME_PERIOD` | `period` | DIRECT |

This coverage deliberately does not create fake null mappings for absent DSD
dimensions. Unknown provider fields remain listed in both the declarative map
and `UNMAPPED_COMTRADE_FIELDS` rather than being silently discarded.
