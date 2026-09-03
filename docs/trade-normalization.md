# Trade normalization

This step adds an application-level interpretation between generic parsing and
any future warehouse ingestion:

```text
UN Comtrade JSON
    |
ParsedObservation
    |
SDMX concept interpretation
    |
source_geo_mapping -> geo_area
    |
NormalizedTradeObservation + normalization issues
```

The normalizer is `normalize_trade_observation` in
`app/pipelines/trade_normalizer.py`. It accepts one `ParsedObservation` and a
database session used only to read structural metadata and geography mappings.
It returns a `NormalizationResult`; it does not add, update, commit, or delete
database records.

## Concepts interpreted

`app/pipelines/trade_concept_mapping.py` declares the interpretation instead of
scattering provider field names through normalization code:

| SDMX concept | Normalized meaning | Preserved provider field |
| --- | --- | --- |
| `REF_AREA` | reference/reporter area | `reporterCode` |
| `COUNTERPART_AREA_1` | counterpart/partner area | `partnerCode` |
| `TRADE_FLOW` | trade-flow code | `flowCode` |
| `FREQ` | frequency code | `freqCode` |
| `COMMODITY_1` | commodity | `cmdCode` plus `classificationCode` |
| `TIME_PERIOD` | observation period | `period` |
| `MEASURE` | not normalized | not exposed by the simplified JSON records |

The real DSD contains `MEASURE`, but the controlled JSON records do not expose a
measure-dimension code. Numeric response fields are therefore retained as
values and are not mislabeled as `MEASURE`. For the same reason, no unit for the
primary value is invented. Provider quantity unit `-1`/`N/A` in the controlled
records is not a usable primary-value unit.

## Source identifiers and canonical geography

Source identifiers are evidence from the provider and remain unchanged in
fields such as `reference_area_source_code`,
`counterpart_area_source_code`, `trade_flow_code`, `frequency_code`, and
`commodity_code`. The complete parsed `source_dimensions`, `source_attributes`,
and `source_fields` are also copied onto the normalized observation.

Canonical geography is separate. A provider reporter or partner code is passed
to the existing resolver in `app/mappings/geo.py`, which reads
`source_geo_mapping` and its linked `geo_area`. The normalizer never matches on
country names and never hardcodes AU membership. From the canonical row it
copies the geography ID, ISO codes, English name, area type, and AU flag.

For the controlled fixtures this produces:

- reporter provider code `788` -> Tunisia (`TN`, `TUN`, `COUNTRY`, AU member);
- partner provider code `0` -> World (no country ISO codes, `AGGREGATE`, not an
  AU member).

Counterparts may be countries, regions, aggregates, or other areas. They do not
need to be AU members.

## Commodity and statistical values

The controlled records keep each commodity representation distinct:

- source classification: `S4` (SITC Rev.4);
- source commodity code: `TOTAL`;
- parsed SDMX commodity code: `SITC4_TOTAL`;
- provider description: `All Commodities`.

`primary_value` comes only from the parser's verified `primaryValue` Decimal.
Additional parser values are copied independently into `quantity`,
`net_weight`, `gross_weight`, `cif_value`, and `fob_value`. Null remains null;
it is never converted to zero. `time_period` remains the source string, such as
`2022`, `2023`, or `2024`.

## Normalization issues

Expected record-level data-quality conditions are returned as structured
`NormalizationIssue` values rather than raising an exception that would stop a
future batch. Current codes are:

- `UNMAPPED_REFERENCE_AREA`
- `UNMAPPED_COUNTERPART_AREA`
- `MISSING_TRADE_FLOW`
- `MISSING_TIME_PERIOD`
- `MISSING_PRIMARY_VALUE`

An unmapped reference area is marked as a fatal normalization issue because
reporter identity and AU eligibility cannot be established. The result still
contains a `NormalizedTradeObservation` candidate with the source code and null
canonical fields so the validation layer can emit `VALID_REFERENCE_AREA`
without fabricating geography. Persistence is impossible unless validation
accepts the candidate.

An unmapped counterpart is nonfatal. The result can contain a normalized
observation with the original counterpart source code, null canonical
counterpart fields, and an `UNMAPPED_COUNTERPART_AREA` issue. This preserves the
record for a later ingestion-policy decision.

## Boundary with later steps

Normalization interprets and preserves parsed evidence. It is distinct from:

- validation, which applies broader consistency and quality rules;
- filtering, which will decide whether a reporter or record is in dataset scope;
- persistence, which will manage ingestion batches, deduplication, acceptance,
  rejection, and warehouse writes.

The normalizer calculates `reference_is_au_member` but does not discard non-AU
observations. **The normalizer does not decide whether observations should be
stored. That belongs to the ingestion pipeline.**

This step creates no `trade_observation`, `ingestion_batch`,
`observation_rejection`, or `stat_dataset` model or write path.
