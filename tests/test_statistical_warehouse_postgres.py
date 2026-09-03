"""PostgreSQL-only verification of the warehouse uniqueness constraint."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import models as db
from app.database.session import engine


pytestmark = pytest.mark.integration


def test_postgresql_rejects_duplicate_dataset_source_key_hash() -> None:
    """Use migrated PostgreSQL DDL and roll every temporary row back."""
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, expire_on_commit=False)
        try:
            dataset = db.StatDataset(
                agency="TEST_STEP_23B",
                dataflow_id="DUPLICATE_CONSTRAINT",
                dataflow_version="1.0",
                dsd_agency="TEST",
                dsd_id="TEST",
                dsd_version="1.0",
                name="Temporary rolled-back PostgreSQL constraint test",
                source_system="TEST",
            )
            reporter = db.GeoArea(
                name_en="Temporary reporter",
                name_fr="Temporary reporter",
                area_type=db.AreaType.OTHER,
                au_member=False,
            )
            session.add_all((dataset, reporter))
            session.flush()
            batch = db.IngestionBatch(dataset_id=dataset.id, source_system="TEST")
            session.add(batch)
            session.flush()

            values = {
                "dataset_id": dataset.id,
                "reference_area_source_code": "TEST",
                "reference_geo_id": reporter.id,
                "trade_flow_code": "M",
                "frequency_code": "A",
                "time_period": "2022",
                "primary_value": Decimal("100"),
                "source_dimensions": {"FREQ": "A", "REF_AREA": "TEST"},
                "source_attributes": {},
                "source_fields": {},
                "source_key": "FREQ=A|REF_AREA=TEST|TIME_PERIOD=2022",
                "source_key_hash": "e" * 64,
                "observation_content_hash": "f" * 64,
                "first_ingestion_batch_id": batch.id,
                "last_ingestion_batch_id": batch.id,
            }
            first = db.TradeObservation(**values)
            session.add(first)
            session.flush()
            assert first.id is not None

            session.add(db.TradeObservation(**values))
            with pytest.raises(IntegrityError) as error:
                session.flush()

            assert error.value.orig.sqlstate == "23505"
            assert (
                error.value.orig.diag.constraint_name
                == "uq_trade_observation_dataset_source_key_hash"
            )
        finally:
            session.close()
            if transaction.is_active:
                transaction.rollback()
