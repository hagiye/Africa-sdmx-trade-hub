# UNSD IMTS to AFR_TRADE mapping registry

> `AFRSTAT:AFR_TRADE` is an independent portfolio demonstration model.
> The mapping does not represent an official AU/STATAFRIC harmonisation
> specification.

Step 26B records reusable mapping metadata between the exact structures
`UNSD:IMTS(1.2)` and `AFRSTAT:AFR_TRADE(1.0)`. It does not transform,
validate, or persist target observations.

```text
UNSD:IMTS(1.2)
        |
        v
 concept mappings
        |
        v
   code mappings
        |
        v
transformation definitions
        |
        v
AFRSTAT:AFR_TRADE(1.0)
```

The project definition is
`mappings/unsd_imts_to_afr_trade_1.0.json`, identified as
`UNSD_IMTS_TO_AFR_TRADE(1.0)`. Its canonical JSON content has a deterministic
SHA-256 checksum. Each persisted concept row carries that checksum, so the
loaded definition can be tied to version-controlled content.

## Mapping concepts

- A **concept mapping** says how a source concept relates to a target concept.
  A source can produce more than one target concept; `COMMODITY_1`, for
  example, contributes both `PRODUCT_SCHEME` and `PRODUCT`.
- A **code mapping** resolves one explicit, classification-aware source code
  to one target codelist code within its parent concept mapping.
- A **transformation definition** stores a safe implementation key such as
  `NORMALIZE_AREA` or `MAP_PRODUCT`. Python remains in source control; no
  executable code is stored in PostgreSQL.
- **DERIVE** means a target value needs multiple pieces of source context.
  It is metadata in this step, not an executed derivation.
- **DROP** is an approved decision to retain the field only in source
  evidence. **DEFER** means the target decision is not established for 1.0.

`DIRECT`, `RENAME`, `TRANSFORM`, `DERIVE`, `DROP`, and `DEFER` describe the
relationship. `DRAFT`, `CONFIRMED`, `MANUAL`, and `DEPRECATED` describe its
governance state. Only `CONFIRMED` rows are eligible for a future automatic
pipeline. Draft unit and confidentiality decisions are therefore invisible
to confirmed-only lookups.

Every lookup includes source agency, structure ID, structure version, target
agency, target structure ID, and target version. A request for AFR_TRADE 2.0
cannot accidentally obtain an AFR_TRADE 1.0 row. Mapping-definition ID and
version provide a second version boundary for mapping policy itself. Optional
validity dates support time-bounded mappings.

## Geography and safe failure

Geography does not introduce a second country crosswalk. Provider identifiers
such as UN Comtrade `788` and `0` resolve through the existing
`source_geo_mapping` table to `geo_area`. The concept registry then records
the target projection: structural `TN` maps to target `TN`, while structural
`W0` maps to target `AFR_WORLD`. Canonical World remains `AGGREGATE`, never
`COUNTRY`.

A missing code returns `UNRESOLVED_CODE`; it never silently passes the source
code through. This applies even to a `DIRECT` concept because semantic
equivalence does not prove codelist equivalence. The only current product is
the classification-aware `SITC4_TOTAL`, which resolves to the pair
`SITC4`/`TOTAL`. Detailed products are deliberately unresolved.

The source API's `primaryValue` is a numeric value, not a unit. `OBS_VALUE`
is structurally direct, but both `MEASURE -> UNIT_MEASURE` and source unit
metadata remain `DEFER`/`DRAFT`. Target support for `USD` is not evidence that
the simplified source field may be assigned that unit.

## Source-target matrix

| Source concept | Target concept | Mapping type | Code mapping? | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| `FREQ` | `FREQ` | DIRECT | `A -> A` | CONFIRMED | Annual is the current MVP. |
| `REF_AREA` | `REF_AREA` | TRANSFORM | `TN -> TN` | CONFIRMED | Provider area first resolves through canonical geography. |
| `TRADE_FLOW` | `TRADE_FLOW` | TRANSFORM | `M -> IMPORT`, `X -> EXPORT` | CONFIRMED | Target codes are explicit words. |
| `COMMODITY_1` | `PRODUCT_SCHEME` | DERIVE | `SITC4_TOTAL -> SITC4` | CONFIRMED | Classification context is mandatory. |
| `COMMODITY_1` | `PRODUCT` | DERIVE | `SITC4_TOTAL -> TOTAL` | CONFIRMED | Detailed products are deferred by absence, not passthrough. |
| `COMMODITY_1_CONF` | `CONF_STATUS` | DEFER | No | DRAFT | Precedence and source exposure are unresolved. |
| `COMMODITY_2` | — | DROP | No | CONFIRMED | Secondary commodity is outside target 1.0. |
| `COMMODITY_2_CONF` | — | DROP | No | CONFIRMED | Depends on secondary commodity. |
| `COMMODITY_CUSTOM_BREAKDOWN` | — | DEFER | No | DRAFT | Needs a future custom-product model. |
| `COUNTERPART_AREA_1` | `COUNTERPART_AREA` | RENAME | `W0 -> AFR_WORLD` | CONFIRMED | Codes still require canonical geography. |
| `COUNTERPART_AREA_1_CONF` | `CONF_STATUS` | DEFER | No | DRAFT | Confidentiality semantics are unresolved. |
| `COUNTERPART_AREA_2` | — | DROP | No | CONFIRMED | Secondary counterpart is outside target 1.0. |
| `COUNTERPART_AREA_2_CONF` | — | DROP | No | CONFIRMED | Depends on secondary counterpart. |
| `TRANSPORT_MODE_BORDER` | — | DEFER | No | DRAFT | Not harmonised in the MVP. |
| `TRANSPORT_MODE_BORDER_CONF` | — | DEFER | No | DRAFT | Not harmonised in the MVP. |
| `CUSTOMS_PROC` | — | DEFER | No | DRAFT | Target semantics are not established. |
| `ACTIVITY` | — | DEFER | No | DRAFT | Outside the aggregate trade MVP. |
| `TRANSFORMATION` | — | DEFER | No | DRAFT | Outside the aggregate trade MVP. |
| `MEASURE` | `UNIT_MEASURE` | DEFER | No | DRAFT | `primaryValue` is not a unit code. |
| `TIME_PERIOD` | `TIME_PERIOD` | DIRECT | No | CONFIRMED | Format is interpreted with frequency. |
| `OBS_VALUE` | `OBS_VALUE` | DIRECT | No | CONFIRMED | Numeric measure metadata only in this step. |
| `COMMENT_OBS` | — | DROP | No | CONFIRMED | Preserved in source evidence. |
| `COMMODITY_CUSTOM_CODE` | — | DEFER | No | DRAFT | Depends on a custom-product model. |
| `COMMODITY_CUSTOM_DESC` | — | DEFER | No | DRAFT | Depends on a custom-product model. |
| `COUNTERPART_AREA_1_ANNOTATION` | — | DROP | No | CONFIRMED | Preserved in source evidence. |
| `COUNTERPART_AREA_1_TYPE` | — | DROP | No | CONFIRMED | Type is held by canonical `geo_area`. |
| `COUNTERPART_AREA_2_ANNOTATION` | — | DROP | No | CONFIRMED | Secondary counterpart is omitted. |
| `COUNTERPART_AREA_2_TYPE` | — | DROP | No | CONFIRMED | Secondary counterpart is omitted. |
| `OBS_STATUS` | `OBS_STATUS` | DEFER | No | DRAFT | Status equivalence is not established. |
| `TRADE_SYSTEM` | — | DEFER | No | DRAFT | Not harmonised in target 1.0. |
| `UNIT_MEASURE` | `UNIT_MEASURE` | DEFER | No | DRAFT | Primary-value unit evidence is incomplete. |
| `UNIT_MULT` | `UNIT_MULT` | DEFER | No | DRAFT | Source assignment is not approved. |

The 19 source dimensions each have exactly one coverage classification (the
two `COMMODITY_1` target rows are both `DERIVE`). All source attributes and
the source primary measure are also explicitly classified. No fake target is
introduced to achieve zero unclassified dimensions.

## Operations

```powershell
alembic upgrade head
python scripts/load_afr_trade_mappings.py
python scripts/show_afr_trade_mappings.py
python scripts/report_mapping_coverage.py
pytest tests/test_afr_trade_mapping_registry.py -v
```

The loader validates source concepts, target concepts, codelists, and codes
against the shared metadata registry before writing. Re-running the same
definition reports zero inserts and preserves row identities.
