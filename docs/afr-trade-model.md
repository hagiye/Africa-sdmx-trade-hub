# Canonical AFR_TRADE model

> **Disclaimer:** AFRSTAT:AFR_TRADE is an independent portfolio demonstration
> structure and is not an official African Union or STATAFRIC SDMX artefact.

`AFRSTAT` is a fictional demonstration agency. Nothing in this model claims
institutional approval, ownership, or standard-setting authority.

## Why a canonical target

The source warehouse preserves `UNSD:IMTS(1.2)` evidence. That source DSD is
rich and provider-oriented, while the portfolio needs a smaller, stable target
for future cross-source harmonisation. `AFRSTAT:AFR_TRADE(1.0)` therefore keeps
the core analytical identity—reporter, partner, flow, product, unit, frequency,
and time—without pretending that fields absent from the simplified Comtrade API
have already been harmonised.

This step defines and registers the target only. It does not map codes,
transform observations, create a target statistical dataset, or write
AFR_TRADE observations.

## Identity

| Artefact | Identity | English label | French label |
| --- | --- | --- | --- |
| Agency | `AFRSTAT` | African Statistics Demonstration Agency | Agence de démonstration des statistiques africaines |
| Dataflow | `AFRSTAT:AFR_TRADE(1.0)` | African Harmonised Merchandise Trade | Commerce harmonisé de marchandises en Afrique |
| DSD | `AFRSTAT:AFR_TRADE(1.0)` | African Harmonised Merchandise Trade Structure | Structure du commerce harmonisé de marchandises en Afrique |
| Concept scheme | `AFRSTAT:CS_AFR_TRADE(1.0)` | African Harmonised Merchandise Trade Concepts | Concepts du commerce harmonisé de marchandises en Afrique |

Version `1.0` is part of every maintainable identity. A breaking structural or
semantic change requires a new version rather than silently changing the
meaning of existing target observations.

## Modeling decisions

| Concept | Role | Why included | Potential source concept(s) | Target representation | Codelist | Requirement / notes |
| --- | --- | --- | --- | --- | --- | --- |
| `FREQ` | Dimension | Interprets time granularity | `FREQ` | String | `CL_FREQ` | Mandatory; only annual is currently ingested, while Q/M syntax remains possible. |
| `REF_AREA` | Dimension | Reporting economy | `REF_AREA` | Canonical area code | `CL_AFR_AREA` | Mandatory; target scope is AU Member State reporters. |
| `COUNTERPART_AREA` | Dimension | Partner country, region, or aggregate | `COUNTERPART_AREA_1` | Canonical area code | `CL_AFR_AREA` | Mandatory; simplifies the primary counterpart only. |
| `TRADE_FLOW` | Dimension | Import/export direction | `TRADE_FLOW` | Explicit semantic code | `CL_TRADE_FLOW` | Mandatory; source codes are not assumed to equal target codes. |
| `PRODUCT_SCHEME` | Dimension | Identifies classification and edition | `COMMODITY_1` classification context | String | `CL_PRODUCT_SCHEME` | Mandatory; prevents collisions between identical codes in HS/SITC editions. |
| `PRODUCT` | Dimension | Identifies the classified product | `COMMODITY_1` | String interpreted with `PRODUCT_SCHEME` | `CL_PRODUCT` | Mandatory; MVP contains only `TOTAL`. |
| `UNIT_MEASURE` | Dimension | States what unit qualifies `OBS_VALUE` | source `MEASURE`, `UNIT_MEASURE`, and primary-value semantics | String | `CL_UNIT_MEASURE` | Mandatory in target; assigning a source value is deferred pending mapping evidence. |
| `TIME_PERIOD` | Time dimension | Observation period | `TIME_PERIOD` | Observational time period | — | Mandatory and interpreted with `FREQ`. |
| `OBS_VALUE` | Primary measure | Carries the numeric statistic | simplified API `primaryValue` under source measure semantics | Decimal | — | Mandatory for a future target observation. |
| `OBS_STATUS` | Attribute | Carries an established quality/estimation status | `OBS_STATUS`, estimation flags | String | `CL_OBS_STATUS` | Conditional; current flags are not yet mapped. |
| `CONF_STATUS` | Attribute | Supports confidentiality handling | commodity/counterpart confidentiality concepts | String | `CL_CONF_STATUS` | Conditional; current JSON does not expose these source dimensions. |
| `UNIT_MULT` | Attribute | Makes numerical scaling explicit | `UNIT_MULT` | Integer | `CL_UNIT_MULT` | Mandatory; MVP permits only `0` (unscaled). |
| `DECIMALS` | Attribute | Controls display precision | no direct current source field | Integer 0–12 | — | Conditional and derived only in a later mapping step. |
| `SOURCE` | Attribute | Records controlled provenance | provider/source-system metadata | String | `CL_SOURCE` | Mandatory; controlled IDs only, never URLs or credentials. |

## Dimension order

| Position | Concept | Role | Codelist |
| ---: | --- | --- | --- |
| 1 | `FREQ` | Dimension | `AFRSTAT:CL_FREQ(1.0)` |
| 2 | `REF_AREA` | Dimension | `AFRSTAT:CL_AFR_AREA(1.0)` |
| 3 | `COUNTERPART_AREA` | Dimension | `AFRSTAT:CL_AFR_AREA(1.0)` |
| 4 | `TRADE_FLOW` | Dimension | `AFRSTAT:CL_TRADE_FLOW(1.0)` |
| 5 | `PRODUCT_SCHEME` | Dimension | `AFRSTAT:CL_PRODUCT_SCHEME(1.0)` |
| 6 | `PRODUCT` | Dimension | `AFRSTAT:CL_PRODUCT(1.0)` |
| 7 | `UNIT_MEASURE` | Dimension | `AFRSTAT:CL_UNIT_MEASURE(1.0)` |
| 8 | `TIME_PERIOD` | Time | — |

## Target codelists

| Codelist | Codes in 1.0 | Scope |
| --- | ---: | --- |
| `CL_AFR_AREA` | 56 | 55 canonical AU Member State ISO alpha-2 codes plus `AFR_WORLD`. |
| `CL_TRADE_FLOW` | 2 | `IMPORT`, `EXPORT`. |
| `CL_FREQ` | 3 | `A`, `Q`, `M`; only A is currently ingested. |
| `CL_PRODUCT_SCHEME` | 1 | `SITC4`. |
| `CL_PRODUCT` | 1 | `TOTAL`; detailed products are deferred. |
| `CL_UNIT_MEASURE` | 1 | `USD`; source assignment is not implemented in this step. |
| `CL_OBS_STATUS` | 2 | `AVAILABLE`, `ESTIMATED`; no source mapping is asserted. |
| `CL_CONF_STATUS` | 2 | `PUBLIC`, `CONFIDENTIAL`; no source mapping is asserted. |
| `CL_UNIT_MULT` | 1 | `0` (units/unscaled). |
| `CL_SOURCE` | 1 | `UN_COMTRADE`, a controlled provenance identifier. |

The flow codes use readable target semantics (`IMPORT` and `EXPORT`) instead of
copying `M` and `X`. A later mapping layer may map provider codes; this design
does not implement that mapping.

### Canonical geography

`CL_AFR_AREA` is resolved from the existing version-controlled canonical
geography reference rather than maintaining a second country list. AU Member
State countries use their genuine ISO alpha-2 identifiers and bilingual
canonical labels. `AFR_WORLD` is an explicitly project-specific aggregate with
no ISO-country claim. Version 1.0 adds no non-AU country because the controlled
source scope currently needs only AU reporters and World as counterpart.

### Product and classification

A single `PRODUCT` dimension is ambiguous: `01` can mean different things in
different classifications or editions. The target therefore uses the pair
`PRODUCT_SCHEME` + `PRODUCT`. The MVP pair is `SITC4` + `TOTAL`, preserving the
classification context of the controlled sample without importing a huge
product hierarchy. Future detailed HS or SITC codes require controlled target
codelist expansion and a versioned mapping design.

### Unit and value

The controlled import fixtures have `primaryValue` equal to `cifvalue`, which
supports a monetary trade-value interpretation, but the simplified response
does not expose a reliable SDMX unit assignment. `CL_UNIT_MEASURE` is therefore
minimal (`USD`) and enables the intended target representation without claiming
that current source rows have already been mapped to it.

The source DSD's `MEASURE` dimension identifies which statistic is being
measured. `UNIT_MEASURE` identifies its unit. Target `OBS_VALUE` is different:
it is the decimal number itself. A future transformation must establish the
measure/unit semantics before copying a source number into `OBS_VALUE`.

### Status, confidentiality, and source

Observation and confidentiality support is structural but conditional. The
provider estimation flags and confidentiality dimensions have not been proven
equivalent to target codes, so no values are fabricated. `SOURCE` uses the
controlled code `UN_COMTRADE`; full URLs and secrets do not belong in an
observation-level provenance code.

## Representation and loading

The version-controlled definition is
`structures/afr_trade/afr_trade_1.0.json`. It explicitly declares itself to be
internal canonical JSON, not SDMX-ML. The loader expands the area code source,
validates identities, labels, components, codelist references, ordering, and
code uniqueness, then hashes canonical JSON with SHA-256.

`scripts/load_afr_trade_structure.py` reuses the existing agency, dataflow, DSD,
concept scheme, concept, codelist, code, dimension, attribute, measure, and
localized-label tables. Equal checksums produce `UNCHANGED`; a changed
definition produces an update. No separate metadata registry is introduced.

## Limitations

- No source-to-target dimension or code mapping exists yet.
- No AFR_TRADE observations or target `stat_dataset` exist yet.
- Detailed product classifications are outside the 1.0 MVP.
- Non-AU country counterparts are not yet included.
- Secondary commodity/partner, transport, customs, activity, transformation,
  and source confidentiality detail remain in source evidence or are deferred.
- The internal JSON may be converted to standards-compliant SDMX-ML in a later
  step; it must not be distributed as if it were already an SDMX exchange file.
