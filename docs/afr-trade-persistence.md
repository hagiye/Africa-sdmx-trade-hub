# AFR_TRADE persistence and dissemination

Step 26D adds an auditable target warehouse for the independent portfolio
structure `AFRSTAT:AFR_TRADE(1.0)`. It is not an official African Union or
STATAFRIC structure or service.

```text
UNSD:IMTS source observation
        |
source validation
        |
versioned mapping registry
        |
AFRSTAT:AFR_TRADE candidate
        |
target DSD and codelist validation
        |
target warehouse or governed rejection
```

Only a transformation with `SUCCESS` status, a complete target identity, and
a valid target-validation summary can enter `afr_trade_observation`. Partial or
invalid candidates remain absent from the target table and generate structured
rows in `harmonization_rejection`.

## Identity, revisions, and lineage

The unique target identity is `(target_dataset_id, target_key_hash)`. Re-running
identical content produces `SKIP`; changed content for the same key produces
`UPDATE`; a new key produces `INSERT`. The record retains its first and latest
harmonization batches, its current source observation, mapping definition and
version, target structure identity, content hash, and the complete mapping
trace.

A target created by another mapping version is rejected as
`MAPPING_VERSION_CONFLICT` unless a caller explicitly authorizes a mapping
revision. The batch runner itself accepts only the mapping version implemented
by the transformer, preventing mislabeled results.

## Operations

```powershell
python scripts/harmonize_trade_data.py
python scripts/show_afr_trade_warehouse.py
python scripts/report_harmonization_quality.py
python scripts/show_observation_lineage.py
```

The read-only statistical REST surface is available at
`/api/v1/afr-trade`, `/api/v1/afr-trade/{observation_id}`, and
`/api/v1/afr-trade/metadata`. It supports exact area, flow, and product filters,
inclusive period filters, and bounded offset pagination. This is deliberately a
small statistical REST interface, not an implementation of the SDMX REST
standard.

The production mapping registry currently defers `UNIT_MEASURE` and
`UNIT_MULT`, and does not define `SOURCE`. Those mandatory target concepts must
be confirmed through mapping governance before the controlled source rows can
be persisted; until then, the expected and correct operational result is a
partial batch with explicit rejections and an empty target warehouse.
