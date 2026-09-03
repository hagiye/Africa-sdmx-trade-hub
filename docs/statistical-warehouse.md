# Statistical warehouse and observation identity

Step 23B adds storage and deterministic identity without adding an ingestion
pipeline. The three controlled UN Comtrade fixtures can be parsed, normalized,
and hashed offline, but the script does not persist them.

```text
NormalizedTradeObservation
        |
        v
canonical source key
        |
        v
dataset-scoped SHA-256 identity
        |
        v
trade_observation
```

## Warehouse tables

`stat_dataset` represents the source statistical dataset. Its identity is the
tuple `(agency, dataflow_id, dataflow_version)`, enforced by
`uq_stat_dataset_source_identity`; its display name is not part of identity.
The table also stores the referenced DSD agency, ID, and version, source system,
optional source URL, and creation/update timestamps.

`ingestion_batch` is an audit envelope prepared for future ingestion. It stores
the dataset and source system, optional query identity and JSONB parameters,
period range, start/finish times, status, seven observation counters, response
and statistical-content checksums, an optional error message, and timestamps.
Statuses are `RUNNING`, `SUCCESS`, `PARTIAL`, and `FAILED`; new batches default
to `RUNNING`, all counters default to zero, and `finished_at` starts null.

`trade_observation` follows the current `NormalizedTradeObservation` model. It
stores the dataset; original reporter/partner codes and canonical geography
foreign keys; flow, frequency, commodity source/classification/SDMX codes and
period; primary value, quantity, net/gross weight, CIF and FOB values; source
dimensions, attributes and fields as JSONB; the readable key and two hashes;
first/last ingestion-batch provenance; and timestamps. Statistical values use
PostgreSQL unconstrained `NUMERIC`, preserving Python `Decimal` values without
asserting a source-wide fixed scale.

`observation_rejection` is evidence storage for future validation. It records
the batch, optional source key/hash, optional concept and invalid value, reason,
severity, message, optional raw observation JSONB, and creation time. Prepared
reason codes are `MISSING_DIMENSION`, `INVALID_CODE`, `INVALID_VALUE`,
`UNMAPPED_REFERENCE_AREA`, `UNMAPPED_COUNTERPART_AREA`, and
`MALFORMED_OBSERVATION`. No validation engine is implemented in this step.

## Observation identity

The source key is built from every populated concept/value pair in the
normalized observation's `source_dimensions`, plus `TIME_PERIOD` from the
normalized field. Any `TIME_PERIOD` entry in `source_dimensions` is removed
first, so time occurs exactly once. Concept IDs are sorted lexicographically and
serialized as unmodified `CONCEPT_ID=value` components joined by `|`. Null
dimensions are omitted. SDMX IDs/codes containing the reserved structural
delimiters are rejected rather than ambiguously serialized.

For the current fixture structure, a key has this form:

```text
COMMODITY_1=SITC4_TOTAL|COUNTERPART_AREA_1=W0|COUNTERPART_AREA_2=W0|FREQ=A|REF_AREA=TN|TIME_PERIOD=2022|TRADE_FLOW=M
```

The canonical dataset identity is exactly:

```text
agency|dataflow_id|dataflow_version
```

The source-key hash input is exactly:

```text
<dataset canonical identity>|<source key>
```

It is encoded as UTF-8 and hashed with SHA-256. For this dataset the prefix is
`UNSD|IMTS_A|1.0|`. Database row IDs, labels, timestamps, response-envelope
metadata, and statistical values are not identity inputs. PostgreSQL enforces
one row per `(dataset_id, source_key_hash)` with
`uq_trade_observation_dataset_source_key_hash`.

## Revision-sensitive content

Observation content is distinct from identity. It is canonical compact JSON
with sorted keys containing:

- `primary_value`, `quantity`, `net_weight`, `gross_weight`, `cif_value`, and
  `fob_value`;
- relevant source unit, aggregation, and quality/status attributes:
  `aggrLevel`, `altQtyUnitCode`, `qtyUnitCode`, `isAggregate`,
  `isAltQtyEstimated`, `isGrossWgtEstimated`, `isLeaf`,
  `isNetWgtEstimated`, `isOriginalClassification`, `isQtyEstimated`,
  `isReported`, and `legacyEstimationFlag`.

The canonical JSON is UTF-8 encoded and SHA-256 hashed. Dictionaries are sorted
recursively and compact separators are fixed. Decimal scale is treated as
presentation rather than statistical content: numerically equal finite values
such as `Decimal("1")`, `Decimal("1.0")`, and `Decimal("1.00")` serialize as
`"1"` and therefore hash identically. Negative and positive zero both serialize
as `"0"`.

Raw `source_fields`, labels, database timestamps, ingestion-batch IDs, and
volatile API envelope fields such as `elapsedTime` do not enter the content
hash.

If the dimensions and period are unchanged while the primary value changes
from X to Y, the source key and source-key hash stay the same, while the content
hash changes. A future ingestion pipeline will interpret that as an update to
the existing row, not a second observation. That pipeline is intentionally not
part of Step 23B.
