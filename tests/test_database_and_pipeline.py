"""Registry constraints and deterministic import-pipeline tests."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import models as db
from app.pipelines.import_structures import import_structures


COUNT_MODELS = (
    db.Dataflow,
    db.DSD,
    db.ConceptScheme,
    db.Concept,
    db.Codelist,
    db.Code,
    db.Dimension,
    db.Attribute,
    db.Measure,
)


def registry_counts(session: Session) -> dict[str, int]:
    return {
        model.__tablename__: session.scalar(select(func.count()).select_from(model))
        or 0
        for model in COUNT_MODELS
    }


def test_dataflow_identity_is_unique(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(db.Agency(agency_id="UNSD", name="UNSD"))
    db_session.flush()
    values = {
        "agency_id": "UNSD",
        "dataflow_id": "IMTS_A",
        "version": "1.0",
        "name": "IMTS Annual",
        "source_url": "https://example.invalid",
        "retrieved_at": now,
        "checksum": "a" * 64,
    }
    db_session.add_all([db.Dataflow(**values), db.Dataflow(**values)])

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_import_is_idempotent_and_preserves_labels(
    db_session: Session, fixture_sdmx_client
) -> None:
    first = import_structures(db_session, fixture_sdmx_client)
    first_counts = registry_counts(db_session)
    second = import_structures(db_session, fixture_sdmx_client)
    second_counts = registry_counts(db_session)

    assert first.status == "SUCCESS"
    assert first.constraints == 1
    assert first_counts == {
        "sdmx_dataflow": 1,
        "sdmx_dsd": 1,
        "sdmx_concept_scheme": 1,
        "sdmx_concept": 2,
        "sdmx_codelist": 1,
        "sdmx_code": 2,
        "sdmx_dimension": 2,
        "sdmx_attribute": 1,
        "sdmx_measure": 1,
    }
    assert second_counts == first_counts
    assert second.inserted == 0
    assert second.updated == 0
    assert second.unchanged == 4
    flow = db_session.scalar(select(db.Dataflow))
    labels = dict(
        db_session.execute(
            select(db.LocalizedLabel.language, db.LocalizedLabel.label).where(
                db.LocalizedLabel.entity_type == "dataflow",
                db.LocalizedLabel.entity_pk == flow.id,
            )
        ).tuples().all()
    )
    assert labels["en"] == "IMTS Annual"
    assert labels["fr"] == "Commerce international annuel"


def test_changed_structure_checksum_updates_without_duplicates(
    db_session: Session, fixture_sdmx_client
) -> None:
    import_structures(db_session, fixture_sdmx_client)
    counts_before = registry_counts(db_session)
    fixture_sdmx_client.payload = fixture_sdmx_client.payload.replace(
        b"IMTS Annual", b"IMTS Annual revised"
    )

    changed = import_structures(db_session, fixture_sdmx_client)

    assert changed.updated == 4
    assert changed.checksum_changes == 4
    assert registry_counts(db_session) == counts_before
    assert db_session.scalar(select(db.Dataflow.name)) == "IMTS Annual revised"
