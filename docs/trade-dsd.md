# Selected trade DSD

- Live source: `https://sdmxcentral.imf.org/sdmx/v2/structure/datastructure/UNSD/IMTS/1.2`
- Structural content SHA-256: `e00b0333b47476f769b1952514ee9a2d583a4816ab50721bbe218bf822779f7e`
- Raw payload SHA-256: `5c0a300dd37d9bacc7dd2a249467c94a946946f414a957d06fc22298ca83e5c5`

- Agency: `UNSD`
- ID: `IMTS`
- Version: `1.2`
- Name: International Merchandise Trade Statistics

## Dimensions

| Position | Concept | Role | Representation | Codelist |
|---:|---|---|---|---|
| 1 | `FREQ` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=SDMX:CL_FREQ(2.0)` | `SDMX:CL_FREQ(2.0)` |
| 2 | `REF_AREA` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_AREA(1.0)` | `UNSD:CL_AREA(1.0)` |
| 3 | `TRADE_FLOW` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_TRADE_FLOW(1.0)` | `UNSD:CL_TRADE_FLOW(1.0)` |
| 4 | `COMMODITY_1` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_COMMODITY(1.0)` | `UNSD:CL_COMMODITY(1.0)` |
| 5 | `COMMODITY_1_CONF` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_COMMODITY(1.0)` | `UNSD:CL_COMMODITY(1.0)` |
| 6 | `COMMODITY_2` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_COMMODITY(1.0)` | `UNSD:CL_COMMODITY(1.0)` |
| 7 | `COMMODITY_2_CONF` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_COMMODITY(1.0)` | `UNSD:CL_COMMODITY(1.0)` |
| 8 | `COMMODITY_CUSTOM_BREAKDOWN` | dimension | `TextFormat(endValue=999999, interval=1, isSequence=true, maxLength=6, startValue=0, textType=BigInteger)` | `-` |
| 9 | `COUNTERPART_AREA_1` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_AREA(1.0)` | `UNSD:CL_AREA(1.0)` |
| 10 | `COUNTERPART_AREA_1_CONF` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_AREA(1.0)` | `UNSD:CL_AREA(1.0)` |
| 11 | `COUNTERPART_AREA_2` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_AREA(1.0)` | `UNSD:CL_AREA(1.0)` |
| 12 | `COUNTERPART_AREA_2_CONF` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_AREA(1.0)` | `UNSD:CL_AREA(1.0)` |
| 13 | `TRANSPORT_MODE_BORDER` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_TRANSPORT_MODE(1.0)` | `UNSD:CL_TRANSPORT_MODE(1.0)` |
| 14 | `TRANSPORT_MODE_BORDER_CONF` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_TRANSPORT_MODE(1.0)` | `UNSD:CL_TRANSPORT_MODE(1.0)` |
| 15 | `CUSTOMS_PROC` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_CUSTOMS_PROC(1.0)` | `UNSD:CL_CUSTOMS_PROC(1.0)` |
| 16 | `ACTIVITY` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_ACTIVITY(1.0)` | `UNSD:CL_ACTIVITY(1.0)` |
| 17 | `TRANSFORMATION` | dimension | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=ESTAT:CL_TRANSFORMATION(1.2)` | `ESTAT:CL_TRANSFORMATION(1.2)` |
| 18 | `MEASURE` | dimension | `urn:sdmx:org.sdmx.infomodel.conceptscheme.ConceptScheme=UNSD:CS_MEASURE(1.0)` | `-` |
| 19 | `TIME_PERIOD` | time | `TextFormat(textType=ObservationalTimePeriod)` | `-` |

## Measures

| Concept | Representation |
|---|---|
| `OBS_VALUE` | `-` |

## Attributes

| Concept | Attachment | Representation | Codelist |
|---|---|---|---|
| `UNIT_MULT` | `Observation` | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=SDMX:CL_UNIT_MULT(1.1)` | `SDMX:CL_UNIT_MULT(1.1)` |
| `UNIT_MEASURE` | `Observation` | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_UNIT_MEASURE(1.0)` | `UNSD:CL_UNIT_MEASURE(1.0)` |
| `COMMENT_OBS` | `Observation` | `TextFormat(textType=String)` | `-` |
| `TRADE_SYSTEM` | `Dimension:REF_AREA` | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_TRADE_SYSTEM(1.0)` | `UNSD:CL_TRADE_SYSTEM(1.0)` |
| `COMMODITY_CUSTOM_CODE` | `Dimension:COMMODITY_CUSTOM_BREAKDOWN` | `TextFormat(textType=String)` | `-` |
| `COMMODITY_CUSTOM_DESC` | `Dimension:COMMODITY_CUSTOM_BREAKDOWN` | `TextFormat(textType=String)` | `-` |
| `COUNTERPART_AREA_1_TYPE` | `Dimension:COUNTERPART_AREA_1` | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_PARTNER_TYPE(1.0)` | `UNSD:CL_PARTNER_TYPE(1.0)` |
| `COUNTERPART_AREA_2_TYPE` | `Dimension:COUNTERPART_AREA_2` | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=UNSD:CL_PARTNER_TYPE(1.0)` | `UNSD:CL_PARTNER_TYPE(1.0)` |
| `COUNTERPART_AREA_1_ANNOTATION` | `Dimension:COUNTERPART_AREA_1` | `TextFormat(textType=String)` | `-` |
| `COUNTERPART_AREA_2_ANNOTATION` | `Dimension:COUNTERPART_AREA_2` | `TextFormat(textType=String)` | `-` |
| `OBS_STATUS` | `Observation` | `urn:sdmx:org.sdmx.infomodel.codelist.Codelist=SDMX:CL_OBS_STATUS(2.1)` | `SDMX:CL_OBS_STATUS(2.1)` |

- Time dimension: `TIME_PERIOD`
- Primary measure: `OBS_VALUE`

The provider uses SDMX 3.0 `Measure`; the first/only measure is reported as the primary measure for this project's inspection output.
