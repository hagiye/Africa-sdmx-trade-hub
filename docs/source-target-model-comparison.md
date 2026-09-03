# UNSD IMTS and AFR_TRADE model comparison

> `AFRSTAT:AFR_TRADE(1.0)` is an independent portfolio demonstration
> structure, not an official African Union or STATAFRIC SDMX artefact.

This is design documentation only. The actions describe a possible future
harmonisation boundary; they are not executable source-to-target mappings.

| Source concept | Target concept | Action | Notes |
| --- | --- | --- | --- |
| `FREQ` | `FREQ` | `DIRECT` | Same analytical role; target uses its own codelist. |
| `REF_AREA` | `REF_AREA` | `DIRECT` | Provider geography will eventually resolve to canonical target area codes. |
| `TRADE_FLOW` | `TRADE_FLOW` | `DERIVE` | Target uses `IMPORT`/`EXPORT`, not assumed source codes. |
| `COMMODITY_1` plus classification context | `PRODUCT_SCHEME`, `PRODUCT` | `DERIVE` | Split prevents collisions across classifications and editions. |
| `COMMODITY_1_CONF` | `CONF_STATUS` | `DEFER` | Not exposed by the current simplified JSON. |
| `COMMODITY_2` | — | `DROP` | Secondary commodity is outside MVP; source evidence remains preserved. |
| `COMMODITY_2_CONF` | — | `DROP` | Depends on omitted secondary commodity and is not currently exposed. |
| `COMMODITY_CUSTOM_BREAKDOWN` | — | `DEFER` | Custom product breakdown needs a later statistical use case. |
| `COUNTERPART_AREA_1` | `COUNTERPART_AREA` | `RENAME` | Primary counterpart is retained under a simpler target name. |
| `COUNTERPART_AREA_1_CONF` | `CONF_STATUS` | `DEFER` | Confidentiality semantics need explicit future mapping. |
| `COUNTERPART_AREA_2` | — | `DROP` | Secondary counterpart is outside the MVP target key. |
| `COUNTERPART_AREA_2_CONF` | — | `DROP` | Depends on omitted secondary counterpart. |
| `TRANSPORT_MODE_BORDER` | — | `DEFER` | Available conceptually in IMTS but not harmonised in current API mapping. |
| `TRANSPORT_MODE_BORDER_CONF` | — | `DEFER` | Transport confidentiality is not exposed or mapped. |
| `CUSTOMS_PROC` | — | `DEFER` | Provider fields exist, but authoritative target semantics are not established. |
| `ACTIVITY` | — | `DEFER` | Not exposed by the simplified API and outside MVP analysis. |
| `TRANSFORMATION` | — | `DEFER` | Not exposed by the simplified API and outside MVP analysis. |
| `MEASURE` | `UNIT_MEASURE` plus observation semantics | `DERIVE` | Source measure identity must be established before assigning target unit/value. |
| `TIME_PERIOD` | `TIME_PERIOD` | `DIRECT` | Format remains conditional on frequency. |
| `OBS_VALUE` / API `primaryValue` | `OBS_VALUE` | `DIRECT` | Numeric value only after measure/unit semantics are proven. |
| `UNIT_MULT` | `UNIT_MULT` | `DIRECT` | Target 1.0 permits unscaled values only; mapping is not yet executed. |
| `UNIT_MEASURE` | `UNIT_MEASURE` | `DEFER` | Simplified source response does not provide an authoritative primary-value unit. |
| `OBS_STATUS` and estimation flags | `OBS_STATUS` | `DEFER` | Equivalence of provider flags and target status codes is not established. |
| commodity/counterpart confidentiality | `CONF_STATUS` | `SIMPLIFY` | One target status is structurally available; precedence rules are deferred. |
| `COMMENT_OBS` | — | `DROP` | Free-text observation commentary is outside the MVP key and attributes. |
| `TRADE_SYSTEM` | — | `DEFER` | Potentially valuable but not yet harmonised. |
| `COMMODITY_CUSTOM_CODE` | — | `DEFER` | Depends on a future custom-product design. |
| `COMMODITY_CUSTOM_DESC` | — | `DEFER` | Depends on a future custom-product design. |
| `COUNTERPART_AREA_1_TYPE` | canonical geography type | `SIMPLIFY` | Country/region/aggregate type is represented by canonical area metadata. |
| `COUNTERPART_AREA_2_TYPE` | — | `DROP` | Secondary counterpart is omitted. |
| counterpart annotations | — | `DROP` | Provider annotations remain in source evidence, not the MVP target. |
| provider/source metadata | `SOURCE` | `DERIVE` | Future mapping will assign a controlled provenance code such as `UN_COMTRADE`. |
| no direct source field | `DECIMALS` | `DEFER` | Display precision requires an explicit future derivation policy. |

## Why the target is smaller

The source DSD is designed for detailed international merchandise trade
exchange. The target MVP is designed for a clear pan-African analytical key.
Omission does not mean the source concepts are unimportant:

- confidentiality, secondary commodity, and secondary counterpart dimensions
  are not exposed in the controlled simplified API records;
- transport mode and customs procedure require semantics not yet harmonised;
- activity and transformation are outside the current aggregate trade use case;
- custom breakdowns need a product-model extension;
- all original fields remain available in the source warehouse even when they
  are not promoted into the canonical target.

No `DIRECT`, `RENAME`, `SIMPLIFY`, `DERIVE`, `DROP`, or `DEFER` row in this
document performs a transformation. Executable mappings belong to a later
step.
