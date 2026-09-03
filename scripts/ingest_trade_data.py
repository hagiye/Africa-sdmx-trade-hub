"""Run the first and only Step 24A Tunisia-to-World live ingestion batch."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.database import models as db
from app.database.session import SessionLocal
from app.pipelines.ingest_trade_data import (
    TradeIngestionError,
    TradeQuery,
    ingest_trade_query,
)
from app.sdmx.comtrade_client import ComtradeClient


CONTROLLED_QUERY = TradeQuery(
    type_code="C",
    frequency_code="A",
    classification_code="S4",
    periods=("2022", "2023", "2024"),
    reporter_code="788",
    flow_code="M",
    partner_code="0",
    partner2_code="0",
    commodity_code="TOTAL",
    max_records=1,
    breakdown_mode="classic",
    include_descriptions=True,
    response_format="JSON",
)
REQUEST_INTERVAL_SECONDS = 1.1


def _resolve_first_run_dataset(session) -> db.StatDataset:
    dataset = session.scalar(
        select(db.StatDataset).where(
            db.StatDataset.agency == "UNSD",
            db.StatDataset.dataflow_id == "IMTS_A",
            db.StatDataset.dataflow_version == "1.0",
        )
    )
    if dataset is None:
        raise RuntimeError("Seed UNSD:IMTS_A(1.0) before ingestion")
    batch_count = session.scalar(
        select(func.count()).select_from(db.IngestionBatch).where(
            db.IngestionBatch.dataset_id == dataset.id
        )
    ) or 0
    observation_count = session.scalar(
        select(func.count()).select_from(db.TradeObservation).where(
            db.TradeObservation.dataset_id == dataset.id
        )
    ) or 0
    if batch_count or observation_count:
        raise RuntimeError(
            "Step 24A ingestion has already been attempted; refusing a second run"
        )
    return dataset


def main() -> int:
    with SessionLocal() as session:
        try:
            dataset = _resolve_first_run_dataset(session)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        last_request_at: float | None = None
        with ComtradeClient(timeout_seconds=settings.sdmx_timeout_seconds) as client:

            def fetch(period: str, parameters: dict[str, str]):
                nonlocal last_request_at
                if last_request_at is not None:
                    remaining = REQUEST_INTERVAL_SECONDS - (
                        time.monotonic() - last_request_at
                    )
                    if remaining > 0:
                        time.sleep(remaining)
                print(f"Requesting controlled UN Comtrade period {period}")
                payload = client.get_trade_data(
                    type_code=CONTROLLED_QUERY.type_code,
                    frequency_code=CONTROLLED_QUERY.frequency_code,
                    classification_code=CONTROLLED_QUERY.classification_code,
                    parameters=parameters,
                )
                last_request_at = time.monotonic()
                records = payload.get("data")
                count = len(records) if isinstance(records, list) else "invalid"
                print(f"Received {count} record(s) for {period}")
                return payload

            try:
                batch = ingest_trade_query(
                    session,
                    dataset_id=dataset.id,
                    query=CONTROLLED_QUERY,
                    fetch_response=fetch,
                )
            except TradeIngestionError as exc:
                print(
                    f"ERROR: ingestion batch {exc.batch_id} failed: {exc}",
                    file=sys.stderr,
                )
                return 1

    print(f"Batch ID: {batch.id}")
    print(f"Status: {batch.status.value}")
    print(f"Received: {batch.observations_received}")
    print(f"Parsed: {batch.observations_parsed}")
    print(f"Accepted: {batch.observations_accepted}")
    print(f"Inserted: {batch.observations_inserted}")
    print(f"Updated: {batch.observations_updated}")
    print(f"Skipped: {batch.observations_skipped}")
    print(f"Rejected: {batch.observations_rejected}")
    return 0 if batch.status is db.IngestionBatchStatus.SUCCESS else 1


if __name__ == "__main__":
    raise SystemExit(main())
