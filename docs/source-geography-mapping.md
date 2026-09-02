# UN Comtrade source geography mapping

Step 22B adds the provider-to-canonical identity bridge without transforming or
ingesting any observation:

```text
UN Comtrade numeric geography code
                ↓
       source_geo_mapping
                ↓
        canonical geo_area
                ↓
       area type / AU membership
```

## Source metadata and identity

The real SDMX structure identifies `UNSD:CL_AREA(1.0)` as the geographic
codelist for `REF_AREA` and both counterpart dimensions. The imported registry
contains that codelist and its structural codes such as `TN`, `KE`, and `W0`.

UN Comtrade's API uses a separate numeric representation. Its official
`partnerAreas.json` reference supplies `PartnerCode`, English label, ISO alpha
codes where applicable, validity dates, and group indicators. Mapping rows use:

```text
source_agency   = UNSD
source_system   = UN_COMTRADE
source_codelist = UNSD:CL_AREA(1.0)
```

Provider codes remain in `source_geo_mapping`; they are never copied into a
canonical area's identity merely because they happen to be numeric. Canonical
identity continues to use the source-neutral ISO/M49 fields established in Step
22A.

## Mapping strategy

The loader creates or updates a mapping row for every provider entry. It applies
the following conservative order:

1. exact current numeric M49 match with compatible provider ISO metadata;
2. exact ISO alpha-2 or alpha-3 match;
3. an existing reviewed `CONFIRMED` mapping when exact evidence is unavailable;
4. a controlled, versioned alias/reference mapping;
5. an existing `MANUAL` override as the final reviewed decision.

Fuzzy name matching is never used. Expired provider entities and provider groups
are not automatically mapped. Codes without a supported canonical target remain
present with `mapping_status=UNMAPPED`, `geo_area_id=NULL`, and their source
label/validity metadata intact.

The mapping statuses mean:

- `CONFIRMED`: verified against provider metadata and authoritative identifiers;
- `AUTO_MATCHED`: resolved algorithmically by exact identifier evidence;
- `MANUAL`: explicitly reviewed or overridden;
- `UNMAPPED`: retained provider code with no trustworthy canonical resolution.

## Required reviewed mappings and World

The small controlled file `data/reference/un_comtrade_geo_confirmed.json`
records the three mappings already evidenced by provider metadata and real
project fixtures:

| Provider code | Structural code | Canonical target | Status |
|---:|---|---|---|
| `788` | `TN` | Tunisia (`TN`, `TUN`) | `CONFIRMED` |
| `404` | `KE` | Kenya (`KE`, `KEN`) | `CONFIRMED` |
| `0` | `W0` | World | `CONFIRMED` |

World is one canonical `geo_area` row with `area_type=AGGREGATE`,
`au_member=false`, French label `Monde`, and no ISO2, ISO3, or numeric country
identifier. Multiple future providers can point to this same row; provider code
`0` exists only on the UN Comtrade mapping.

## Resolution and reporter eligibility

`app.mappings.geo.resolve_source_area()` returns the mapped canonical area or
`None` for absent and unresolved codes. It never raises `KeyError` or pretends an
unknown code is a country.

`is_au_reporter()` is true only when the resolved canonical area is both a
`COUNTRY` and an AU member. Therefore Tunisia (`788`) and Kenya (`404`) qualify,
while World (`0`) does not.

This reporter rule is intentionally different from partner eligibility. A
partner may be an AU or non-AU country, region, or aggregate. Tunisia-to-World
and a future Tunisia-to-France observation are both valid shapes. Step 22B only
documents this rule and exposes resolution helpers; it does not filter or
normalize observations.

## Idempotency and layer boundary

The loader's uniqueness key is source agency, system, codelist, and code. It
updates only mapping-owned fields, does not delete stale or unrelated mappings,
and reports examined, inserted, updated, unchanged, mapped, and unmapped counts.

No `trade_observation`, ingestion batch, normalized trade record, rejection,
`AFR_TRADE` structure, or dataset filter is created in this step.
