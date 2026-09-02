# Canonical African geography reference

Step 22A creates the canonical side of geographic identity. It does not map any
UN Comtrade code, parse observations, filter trade, or build a warehouse.

```text
UN Comtrade codes
        ↓
  [future mapping]
        ↓
Canonical geo_area
        ↓
ISO identifiers / labels / AU membership
```

The source-system mapping shown above belongs to Step 22B.

## Sources and scope

The versioned file `data/reference/au_member_states.json` combines two
authoritative sources, verified on 2026-09-02:

- the [African Union Member States roster](https://www.au.int/en/member_states/countryprofiles2),
  which identifies the current 55 AU members;
- the [United Nations Statistics Division M49 list](https://unstats.un.org/unsd/methodology/m49/overview/),
  which supplies ISO alpha-2, ISO alpha-3, three-digit M49 identifiers, English
  and French names, and geographic groupings.

All reference rows are countries for this checkpoint. `World` is deliberately
deferred; if added in Step 22B or later it must be an `AGGREGATE`, never a
country and never an AU member.

The AU roster's Sahrawi Arab Democratic Republic entry is represented by the
UN M49/ISO identifiers `EH`, `ESH`, and `732`; its canonical UN M49 English and
French labels are `Western Sahara` and `Sahara occidental`. This preserves the
AU membership assertion while keeping the canonical identifier labels faithful
to the selected statistical standard.

`region` is the UN M49 region `Africa`. `subregion` is the most specific M49
African grouping: Northern, Eastern, Middle, Southern, or Western Africa. These
are UN statistical groupings, not the separate AU five-region classification.

## Canonical identity and labels

`geo_area` uses an internal database primary key, while cross-system canonical
identity relies on ISO alpha-2, ISO alpha-3, and three-digit numeric identifiers.
The ISO fields are nullable because future regions and aggregates may not have
ISO country codes. Partial unique indexes enforce uniqueness whenever an
identifier is present.

English and French names are labels, not keys. Both are retained directly from
UN M49 rather than generated or translated by the application. Renaming a label
therefore does not change the canonical identity of an area.

The `AreaType` values are:

- `COUNTRY`
- `REGION`
- `AGGREGATE`
- `OTHER`

AU membership is a boolean `au_member` property on the canonical area. Every
row in this intentionally AU-specific reference file has `au_member=true` and
`area_type=COUNTRY`.

## Loader ownership and idempotency

`scripts/load_geo_reference.py` validates the reference file, identifies rows
by canonical ISO identifiers, and inserts missing rows. On existing matching
rows it compares and updates only the fields managed by this reference:

```text
iso2, iso3, numeric_code, name_en, name_fr,
area_type, au_member, region, subregion
```

It does not delete unrelated `geo_area` rows and does not overwrite validity
dates. Each run reports inserted, updated, unchanged, and total counts. A second
run against unchanged reference data creates no duplicates.

Provider-specific values such as UN Comtrade `788`, `404`, or `0` are not stored
as mappings here. Although a canonical M49 numeric identifier may have the same
digits, its presence in `numeric_code` is source-neutral; linking a provider's
code system to that identifier remains Step 22B work.
