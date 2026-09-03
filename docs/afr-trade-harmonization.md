# AFR_TRADE in-memory harmonization

> `AFRSTAT:AFR_TRADE` is an independent portfolio demonstration structure.
> It is not an official African Union or STATAFRIC standard, and this workflow
> is not an official AU/STATAFRIC harmonisation specification.

Step 26C introduces a non-persistent target model, registry-driven
transformation, mapping trace, deterministic target serialization and hashes,
and target validation. It deliberately creates no harmonized database table.

```text
UNSD:IMTS observation
        |
        v
UNSD source validation
        |
        v
versioned mapping registry
        |
        v
AFR_TRADE target candidate + mapping trace
        |
        v
AFR_TRADE target DSD/codelist validation
        |
        v
harmonized output only when valid
```

## Why validation happens twice

Source validation proves that an observation is coherent under
`UNSD:IMTS(1.2)` and the project's current Comtrade application scope. It
cannot prove that transformed values satisfy `AFRSTAT:AFR_TRADE(1.0)`.
Transformation can change codes, split one source concept into several target
concepts, or encounter incomplete policy. Target validation therefore reloads
the actual target DSD and codelists and independently checks:

- all mandatory dimensions and attributes;
- target frequency, geography, trade-flow, product, unit, status and source
  codes where present;
- `TIME_PERIOD` syntax relative to `FREQ`;
- a present, finite Decimal `OBS_VALUE`;
- the target `DECIMALS` range when supplied.

The target model is `AfrTradeObservation`, not a reused
`NormalizedTradeObservation`. It contains exactly the eight target dimensions,
the `OBS_VALUE` primary measure, and the five target attributes defined in
AFR_TRADE 1.0. Optional Python values permit a partial candidate to retain
successful mappings while validation reports mandatory gaps.

## Registry and governance behavior

Production lookup always requests `CONFIRMED` concept and code mappings.
`DRAFT` mappings are not evidence, `DEPRECATED` mappings are not current, and
`DEFER` decisions are explicitly reported as `DEFERRED_MAPPING`. Missing code
mappings produce `MISSING_CODE_MAPPING`; the transformer never copies an
unknown source code into the target.

Frequency, geography, flow and product target values come from persisted code
mappings. Geography additionally must resolve through the existing
`source_geo_mapping -> geo_area` bridge. The World partner remains the
canonical `AGGREGATE` and maps from structural `W0` to `AFR_WORLD`.

Every source-target decision creates a trace row with source concept/value,
target concept/value, mapping type, governance status, transformation ID and
outcome. Explicit `DROP` decisions appear as `DROPPED`; `DEFER` decisions
appear as `DEFERRED`. This preserves an audit explanation even when the source
field is absent from the simplified provider record.

## Current real-fixture result

The confirmed registry successfully maps the analytical core of all three
controlled Tunisia observations:

| Period | REF_AREA | Counterpart | Flow | Product | Unit | OBS_VALUE | Target validation |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| 2022 | `TN` | `AFR_WORLD` | `IMPORT` | `SITC4/TOTAL` | deferred | `26672667450.171` | INVALID / PARTIAL |
| 2023 | `TN` | `AFR_WORLD` | `IMPORT` | `SITC4/TOTAL` | deferred | `25930493874.99` | INVALID / PARTIAL |
| 2024 | `TN` | `AFR_WORLD` | `IMPORT` | `SITC4/TOTAL` | deferred | `26065070572.389` | INVALID / PARTIAL |

This is not forced into success. AFR_TRADE 1.0 requires `UNIT_MEASURE`,
`UNIT_MULT`, and `SOURCE`, but Step 26B intentionally left measure/unit
decisions as `DRAFT`/`DEFER` and defined no source-system-to-`SOURCE` mapping.
Consequently:

- `primaryValue` correctly becomes Decimal `OBS_VALUE`, never a unit;
- no `USD`, multiplier `0`, or `UN_COMTRADE` value is invented;
- target validation reports those three mandatory concepts as missing;
- each real result is `PARTIAL`, not publishable harmonized output;
- completing those mappings requires separately approved statistical evidence
  and a versioned registry update.

## Interview example: Tunisia imports from World, 2023

The source observation is `UNSD:IMTS(1.2)`, reporter Tunisia, partner World,
imports, SITC Revision 4 total merchandise, period `2023`, with
`primaryValue=25930493874.99`.

| Target concept | Source concept | Source value | Target value | Decision |
| --- | --- | --- | --- | --- |
| `FREQ` | `FREQ` | `A` | `A` | DIRECT / CONFIRMED |
| `REF_AREA` | `REF_AREA` | provider `788`, structural `TN` | `TN` | TRANSFORM / CONFIRMED through canonical geography |
| `COUNTERPART_AREA` | `COUNTERPART_AREA_1` | provider `0`, structural `W0` | `AFR_WORLD` | RENAME / CONFIRMED through canonical geography |
| `TRADE_FLOW` | `TRADE_FLOW` | `M` | `IMPORT` | TRANSFORM / CONFIRMED |
| `PRODUCT_SCHEME` | `COMMODITY_1` | `SITC4_TOTAL` | `SITC4` | DERIVE / CONFIRMED |
| `PRODUCT` | `COMMODITY_1` | `SITC4_TOTAL` | `TOTAL` | DERIVE / CONFIRMED |
| `TIME_PERIOD` | `TIME_PERIOD` | `2023` | `2023` | DIRECT / CONFIRMED |
| `OBS_VALUE` | `OBS_VALUE` | `25930493874.99` | `25930493874.99` | DIRECT / CONFIRMED |
| `UNIT_MEASURE` | `MEASURE` / `UNIT_MEASURE` | unavailable | — | DEFER / DRAFT |
| `UNIT_MULT` | `UNIT_MULT` | unavailable | — | DEFER / DRAFT |
| `SOURCE` | source-system metadata | `UN_COMTRADE` | — | no mapping definition |

Source validation passes. Target validation runs and returns `INVALID` for the
three missing mandatory target concepts, so harmonization returns `PARTIAL`.

## Canonical JSON and hashes

`AfrTradeObservation.canonical_json()` emits deterministic **AFR_TRADE
canonical JSON**. It is not labeled SDMX-JSON because no standards-compliant
SDMX-JSON envelope has been implemented.

Target identity hashes include the exact target identity
`AFRSTAT:AFR_TRADE(1.0)` and all target dimensions, including `TIME_PERIOD`.
They exclude `OBS_VALUE`. Target content hashes include `OBS_VALUE` and target
attributes. Therefore a value revision retains identity but changes content;
changing period or counterpart changes identity. An incomplete target
candidate has no identity hash because mandatory identity dimensions are
missing.

## Commands

```powershell
python scripts/transform_trade_fixtures.py
python scripts/show_harmonization_trace.py
pytest tests/test_afr_trade_transformer.py -v
pytest -v
alembic check
```
