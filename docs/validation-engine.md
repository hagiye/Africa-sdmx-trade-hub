# SDMX-aware validation engine

The validation layer sits between normalization and warehouse decisions:

```text
DSD + codelists + canonical geography + application rules
                            |
             normalized observation
                            |
                   validation engine
                            |
          INFO / WARNING / ERROR / FATAL
                            |
                 accept or reject
```

`ValidationContext` loads the selected dataset's DSD dimensions, associated
codelist codes, concept names, and source-to-canonical geography mappings once
per batch. Rules reuse those dictionaries, avoiding a database query for every
rule and observation. The default ruleset is explicitly for current
`UNSD:IMTS_A(1.0)` ingestion; it is not imposed on unrelated future datasets.

## Severity and decisions

| Severity | Meaning | Rejects? |
| --- | --- | --- |
| `INFO` | Informational context | No |
| `WARNING` | Observation may continue but merits review | No |
| `ERROR` | Observation fails a rule and should normally be rejected | Yes |
| `FATAL` | Validation cannot safely continue for that observation | Yes |

`ValidationSummary.is_valid` is true when no `ERROR` or `FATAL` exists, and
`should_reject` is true when either exists. An unexpected exception inside one
rule becomes a controlled `FATAL` finding named `VALIDATION_RULE_EXCEPTION`;
the exception and stack trace are not exposed and the rest of the batch can
continue.

## Structural versus application validation

The distinction is deliberate. `VALID_TRADE_FLOW_CODE` is SDMX/codelist
validation: it asks whether the value exists in the codelist linked to
`TRADE_FLOW` by `UNSD:IMTS(1.2)`. `REFERENCE_AREA_IS_AU_MEMBER` is an
`APPLICATION_SCOPE` rule: SDMX permits many reporters, but this warehouse
currently accepts only canonical AU Member State countries as reporters.
World is valid canonical geography and a valid counterpart aggregate; it is
outside application scope when used as the reporter.

## Current API mapping compromise

The full IMTS DSD has 19 dimensions. The simplified Comtrade JSON response does
not expose all of them, notably `MEASURE`, confidentiality dimensions, activity,
and transformation. `MANDATORY_DIMENSION_PRESENT` therefore checks only the
dimensions actually represented by the current confirmed application mapping:
`FREQ`, `REF_AREA`, `TRADE_FLOW`, `COMMODITY_1`,
`COUNTERPART_AREA_1`, `COUNTERPART_AREA_2`, and `TIME_PERIOD`. It does not
fabricate values for unexposed DSD dimensions. This source-specific required set
can be replaced when a richer SDMX representation is ingested.

Frequency, flow, and commodity values are checked against codelists associated
with the DSD in the metadata registry. `A` is not hardcoded as the only valid
frequency. Commodity validation uses the classification-aware normalized code
(`SITC4_TOTAL` for source `S4:TOTAL`), not a universal handwritten commodity
list.

## Rules

| Rule ID | Category | Failure severity | Concept | Purpose |
| --- | --- | --- | --- | --- |
| `MANDATORY_DIMENSION_PRESENT` | `STRUCTURE` | `ERROR` | relevant dimension | Requires dimensions exposed by the current API mapping. |
| `VALID_FREQUENCY_CODE` | `CODELIST` | `ERROR` (`FATAL` if metadata unavailable) | `FREQ` | Uses the DSD-associated frequency codelist. |
| `VALID_TRADE_FLOW_CODE` | `CODELIST` | `ERROR` (`FATAL` if metadata unavailable) | `TRADE_FLOW` | Uses the DSD-associated flow codelist. |
| `VALID_COMMODITY_CODE` | `CODELIST` | `ERROR` (`FATAL` if metadata unavailable) | `COMMODITY_1` | Validates the classification-aware commodity code. |
| `VALID_REFERENCE_AREA` | `GEOGRAPHY` | `ERROR` | `REF_AREA` | Requires source mapping to canonical geography. |
| `REFERENCE_AREA_IS_AU_MEMBER` | `APPLICATION_SCOPE` | `ERROR` | `REF_AREA` | Requires a canonical AU Member State country reporter. |
| `VALID_COUNTERPART_AREA` | `GEOGRAPHY` | `WARNING` | `COUNTERPART_AREA_1` | Flags but retains an unmapped counterpart. |
| `VALID_TIME_PERIOD` | `VALUE` | `ERROR` | `TIME_PERIOD` | Applies frequency-aware `A`, `Q`, or `M` period syntax. |
| `PRIMARY_VALUE_PRESENT` | `VALUE` | `ERROR` | `OBS_VALUE` | Enforces current policy that accepted trade rows need a primary value. |
| `VALID_OBSERVATION_VALUE` | `VALUE` | `ERROR` | `OBS_VALUE` | Requires a finite `Decimal`; missing is handled separately. |
| `NON_NEGATIVE_TRADE_VALUE` | `VALUE` | `WARNING` | `OBS_VALUE` | Flags negative merchandise values for review without inventing a global rejection rule. |
| `DUPLICATE_OBSERVATION_IN_BATCH` | `QUALITY` | `WARNING` | — | Detects a repeated source hash inside one incoming batch. |
| `VALIDATION_RULE_EXCEPTION` | `QUALITY` | `FATAL` | — | Engine safeguard for an unexpected rule failure. |

Within-batch duplication is distinct from an identity already in the warehouse.
An existing warehouse identity remains valid and can lead to `SKIP` or `UPDATE`
according to content hashes.

## Persistence

Every finding is stored in `validation_result`. Accepted warnings link to
`trade_observation`; rejected findings link to `observation_rejection`. The
table records batch, optional observation/rejection, source-key hash, rule,
category, severity, concept, invalid value, safe message, metadata, and creation
time. The rejection message is taken from the primary blocking result so the
two records do not disagree. Counts are queried from this table instead of
adding redundant columns to `ingestion_batch`.

The primary value is required by current warehouse policy because the observed
provider records use it as their selected trade statistic. Missing remains
missing and is never converted to zero. Negative values receive a warning, not
automatic rejection: the registry does not yet encode enough measure-specific
sign policy to justify a universal rule.

Malformed numeric strings are rejected by the parser before normalization in
normal ingestion. `VALID_OBSERVATION_VALUE` remains a defensive validation rule
and is tested with a deliberately constructed malformed normalized object.

## Offline inspection

`python scripts/validate_trade_fixtures.py` validates the three controlled real
fixtures without network calls or warehouse writes. `python
scripts/report_validation_quality.py` reports findings for the latest stored
batch. A batch created before this engine normally has no result rows; the
report says so rather than implying it was validated.
