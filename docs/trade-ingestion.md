# Controlled UN Comtrade ingestion

Step 24A introduces the first bounded production-like observation ingestion:

```text
UN Comtrade preview API
        |
        v
bounded JSON response
        |
        v
generic parser -> trade normalizer -> canonical geography
                                      |
                                      v
                              AU reporter rule
                                      |
                                      v
                         identity and content hashes
                                      |
                                      v
                     trade_observation + ingestion_batch
```

It is not a bulk loader. The production script is deliberately limited to
Tunisia (`reporterCode=788`), World (`partnerCode=0`, `partner2Code=0`), annual
imports, SITC Rev.4 total commodity, and periods 2022, 2023, and 2024. It uses
the unauthenticated preview endpoint with `maxRecords=1` for each period and a
64 KiB response cap. For Step 24B, the script requires exactly the Step 24A
state of one prior batch and three observations. After it creates the second
batch it refuses another run, preventing an accidental third live execution.

The reporter code in the query is not an authorization rule. Every normalized
record is resolved through `source_geo_mapping` to `geo_area`, and the shared
`is_au_reporter()` helper accepts it only when the canonical area is both a
country and an African Union Member State. Tunisia resolves to country `TN` /
`TUN` with `au_member=true`. Counterparts need not be AU members: World resolves
to an identifier-free `AGGREGATE` with `au_member=false` and is valid. An
unmapped counterpart may remain nullable and does not by itself reject a row.

## Batch lifecycle and traceability

`ingest_trade_query()` creates and commits a `RUNNING` batch before invoking the
response fetcher. This gives every inserted row or rejection a stable batch ID.
It records deterministic query JSON, the period range, and actual received,
parsed, accepted, inserted, updated, skipped, and rejected counts.

Each response is parsed by the existing generic parser and normalized by the
existing trade normalizer. Persisted observations retain `source_dimensions`,
`source_attributes`, and the complete source record in `source_fields`; API
envelope metadata is not copied into observations.

On complete success the batch becomes `SUCCESS`. Accepted and rejected records
together produce `PARTIAL`. A batch with no accepted observations becomes
`FAILED`. An unexpected provider, parser, or transaction failure rolls back
pending observation work and then finalizes the already-created batch as
`FAILED`, with a compact error message rather than a stack trace. Every handled
terminal state records `finished_at`.

## Insert, skip, update, and rejection

For every accepted normalized record, the service builds the Step 23B source
key, dataset-scoped source-key hash, and revision-sensitive content hash.

- No row with `(dataset_id, source_key_hash)`: insert it, setting both first and
  last ingestion batch IDs to the current batch.
- Same identity and same content hash: leave statistical content unchanged,
  point `last_ingestion_batch_id` to the current batch, and increment
  `observations_skipped`.
- Same identity and different content hash: update statistical values, source
  traceability, content hash, and last ingestion batch ID; retain the original
  first ingestion batch ID and increment `observations_updated`.
- Out-of-scope, unmapped/non-AU reporter, missing period/value, or normalization
  problem: store one `observation_rejection` with the raw record and increment
  `observations_rejected`.

## Idempotent ingestion

The pair of dataset ID and source-key hash identifies the statistical
observation. If that identity and its content hash match an existing row, the
incoming record is unchanged and the action is `SKIP`. It does not create a row
or rewrite statistical values. A new `ingestion_batch` is still required:
successful no-change checks are real, auditable provider interactions with
their own time, query metadata, checksums, and counters.

`first_ingestion_batch_id` means the batch that originally inserted the
observation and never changes during skips or revisions.
`last_ingestion_batch_id` means the latest successful batch in which the
observation was seen. It therefore advances on `SKIP` as well as `UPDATE`.
Updating this provenance field may advance the row's general `updated_at`, but
does not change its identity, statistical values, source content, or content
hash.

Canonical source keys, observation content, and JSON checksums sort dictionary
keys. Reordered JSON objects therefore remain unchanged. Volatile response
envelope fields such as `elapsedTime` may change raw checksums but do not enter
statistical checksums or observation content hashes.

Within one response, the first copy of an identical record inserts and later
copies skip. Across batches, all copies skip when already stored.

## Duplicate protection

Application logic first selects by `(dataset_id, source_key_hash)` and applies
insert, skip, or update semantics. A possible concurrent insert is attempted
inside a savepoint; if PostgreSQL reports the named identity uniqueness
constraint, the service reloads the winning row and applies skip/update logic.
Other integrity errors remain fatal.

The final protection is PostgreSQL's
`UNIQUE(dataset_id, source_key_hash)` constraint. It remains authoritative even
if two workers race after both application-level lookups find no row. No
distributed lock is introduced.

## Step 24B observed result

The controlled second live batch received, parsed, and accepted the same three
2022–2024 observations. It inserted 0, updated 0, skipped 3, and rejected 0.
The warehouse remained at three rows with no duplicate identity groups.
`first_ingestion_batch_id` remained batch 2 and `last_ingestion_batch_id`
advanced to batch 3 for every row.

Both batches produced statistical checksum
`0cd2274f54d61a7b8ca02cd539c60b3f40a86607da2073b054c20f4c4d5d1ca7`.
Their raw checksums differed because the provider response envelope changed,
which correctly did not create an observation revision.

## Batch checksums

The parser calculates a raw-response checksum (including envelope metadata) and
a statistical-content checksum (records only) for every period. The batch
checksum strategy is identical for each kind:

1. form objects containing `period` and its per-response checksum;
2. sort that list by period;
3. serialize it as UTF-8 canonical JSON with sorted keys and compact separators;
4. calculate SHA-256.

Consequently provider timing fields can change the batch raw checksum but do
not become observation revisions and do not change the batch statistical
checksum.

## Commands

```powershell
alembic upgrade head
alembic check
pytest tests/test_trade_ingestion.py -v
pytest tests/test_trade_ingestion_idempotency.py -v
pytest -v
python scripts/ingest_trade_data.py
python scripts/show_trade_warehouse.py
python scripts/report_ingestion_quality.py
python scripts/compare_ingestion_batches.py
```

Default tests use the committed fixtures and never contact UN Comtrade. The
explicitly marked live integration test performs a read-only one-period probe
and is excluded by the default pytest marker configuration.
