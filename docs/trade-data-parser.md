# Generic UN Comtrade observation parser

Step 21B adds an offline, provider-boundary parser:

```text
UN Comtrade JSON
    -> declarative field mapping
    -> generic parser
    -> ParsedDataResponse
         -> ParsedObservation[]
```

It parses statistical records only. It does not write PostgreSQL rows, apply AU
membership rules, perform geography normalization, construct a trade warehouse,
or create an `AFR_TRADE` dataflow.

## Entry point and models

`app.sdmx.data_parser.parse_comtrade_response()` accepts an already-decoded JSON
response and returns `ParsedDataResponse`. Response-level information includes
the provider and Dataflow identity, parsed record count, envelope metadata, and
both checksum forms.

Each generic `ParsedObservation` contains:

- optional Dataflow agency, ID, and version;
- `dimension_values`, keyed by SDMX concept ID;
- `time_period` as a separate string;
- `observation_values`, keyed by the actual Comtrade value-field name;
- descriptive provider `attributes`;
- the complete original record in `source_fields`;
- its zero-based `source_record_index` and provider `source`.

Reporter, counterpart, trade flow, and commodity are intentionally not bespoke
model properties. They remain SDMX concepts inside `dimension_values`, keeping
the parsed model reusable for other dataflows and later normalization stages.

## Dimensions and time

The parser executes the confirmed rules declared in
`app/sdmx/comtrade_field_mapping.py`; it does not duplicate those mappings.
For the controlled fixtures it populates:

| SDMX concept | Parsed value | Provider evidence |
|---|---|---|
| `FREQ` | `A` | `freqCode` |
| `REF_AREA` | `TN` | confirmed translation from `reporterCode=788` |
| `TRADE_FLOW` | `M` | `flowCode` |
| `COMMODITY_1` | `SITC4_TOTAL` | confirmed `S4` + `TOTAL` composite |
| `COUNTERPART_AREA_1` | `W0` | confirmed translation from `partnerCode=0` |
| `COUNTERPART_AREA_2` | `W0` | confirmed translation from `partner2Code=0` |

No unsupported DSD dimension is inserted, even with a null value. An unknown
provider code or a missing source field leaves that dimension absent while the
original provider value remains available in `source_fields`. This avoids
claiming SDMX codes not supported by Step 21A evidence.

`TIME_PERIOD` is held separately as `time_period`, not duplicated in
`dimension_values`. It always remains a string, so annual (`2024`), quarterly,
and monthly lexical forms can be retained without false datetime semantics.
`canonical_dimension_key()` combines populated dimensions with `TIME_PERIOD`,
sorts concept IDs, and returns a deterministic, unhashed serialization.

## Values, attributes, and source fields

The statistical value fields come from the Step 21A declarative mapping:

```text
altQty, cifvalue, fobvalue, grossWgt, netWgt, primaryValue, qty
```

Present numeric values become `Decimal`; JSON null remains `None`; absent fields
remain absent. `Decimal(str(json_float))` avoids adding binary floating-point
artifacts beyond the lexical decimal exposed by Python's JSON decoder. Numeric
strings and integers are supported, whitespace-only strings become `None`, and
invalid, boolean, non-finite, or unsupported values raise
`ComtradeDataParseError` rather than silently becoming zero.

`get_primary_value()` returns the `primaryValue` entry for convenience. It does
not equate that number with the SDMX `MEASURE` dimension: `MEASURE` identifies a
statistic, whereas the number is observation content. Since Comtrade's simplified
record does not expose an evidenced measure code, `MEASURE` stays absent.

Attributes contain actual descriptive metadata selected in the declarative
mapping, including aggregation information, unit fields, descriptions, and
provider estimation/reporting flags. They are retained under their provider
names; no unproven conversion to `OBS_STATUS` or another SDMX attribute occurs.

`source_fields` is a deep copy of the entire original observation object,
including unknown and unresolved fields. It excludes top-level `count`,
`elapsedTime`, and `error`, which belong to response `envelope_metadata`. This
separation preserves auditability and enables future remapping without treating
volatile envelope timing as statistical data.

## Response and error behavior

A valid `data: []` response returns an empty observation list and record count
zero. Invalid top-level types, missing/wrong observation containers, non-object
records, and invalid numeric values raise `ComtradeDataParseError` with response,
record-index, or field context rather than leaking incidental `KeyError` or
`TypeError` exceptions.

The response exposes both Step 21A checksum concepts. The raw checksum covers
the complete canonical envelope, while the statistical-content checksum covers
only complete records in `data`. Changing only `elapsedTime` therefore affects
the raw checksum but not the statistical checksum; changing `primaryValue`
affects the statistical checksum.

## Layer boundary

AU membership is intentionally absent because it is geography and product
policy, not provider response parsing. Database ingestion, rejection handling,
dataset construction, and uniqueness hashing belong to later checkpoints. This
layer only converts a valid provider response into auditable generic parsed
objects.

## Verification warning

The full test suite continues to report one warning from the installed
third-party `fastapi.testclient` module: its use of `httpx` with Starlette's test
client is deprecated in favor of `httpx2`. Step 21B does not change that
dependency combination. Updating the test-client dependency stack is unrelated
to observation parsing and could affect the existing API tests, so the warning
is recorded here rather than suppressed or changed in this checkpoint.
