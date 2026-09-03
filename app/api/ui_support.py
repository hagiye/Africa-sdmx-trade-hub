"""Small read-only aggregates used by the statistical data explorer UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import models as db
from app.database.session import get_db
from app.pipelines.observation_identity import canonical_decimal


router = APIRouter(prefix="/api/v1", tags=["Data explorer support"])


def _value(value: object) -> object:
    return getattr(value, "value", value)


@router.get("/summary")
def get_statistical_summary(session: Session = Depends(get_db)) -> dict[str, object]:
    target = session.execute(
        select(
            func.count(db.AfrTradeObservation.id),
            func.count(func.distinct(db.AfrTradeObservation.ref_area)),
            func.count(func.distinct(db.AfrTradeObservation.counterpart_area)),
            func.count(func.distinct(db.AfrTradeObservation.time_period)),
            func.min(db.AfrTradeObservation.time_period),
            func.max(db.AfrTradeObservation.time_period),
        )
    ).one()
    source_count = session.scalar(
        select(func.count()).select_from(db.TradeObservation)
    ) or 0
    return {
        "harmonised_observations": target[0],
        "reporting_countries": target[1],
        "counterpart_areas": target[2],
        "available_periods": {
            "count": target[3],
            "earliest": target[4],
            "latest": target[5],
        },
        "source_observations": source_count,
        "source_dataset": "UNSD:IMTS(1.2)",
        "target_dataflow": "AFRSTAT:AFR_TRADE(1.0)",
        "target_dsd_version": "1.0",
    }


@router.get("/validation/summary")
def get_validation_summary(session: Session = Depends(get_db)) -> dict[str, int]:
    severity_counts = dict(
        session.execute(
            select(db.ValidationFinding.severity, func.count(db.ValidationFinding.id))
            .group_by(db.ValidationFinding.severity)
        ).all()
    )
    return {
        "validated_observations": session.scalar(
            select(func.count()).select_from(db.TradeObservation)
        ) or 0,
        "warnings": int(severity_counts.get("WARNING", 0)),
        "errors": int(severity_counts.get("ERROR", 0))
        + int(severity_counts.get("FATAL", 0)),
        "rejected": session.scalar(
            select(func.count()).select_from(db.ObservationRejection)
        ) or 0,
    }


@router.get("/validation/rules")
def get_validation_rules(session: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = session.execute(
        select(
            db.ValidationFinding.rule_id,
            db.ValidationFinding.category,
            db.ValidationFinding.severity,
            db.ValidationFinding.concept_id,
            func.count(db.ValidationFinding.id),
        )
        .group_by(
            db.ValidationFinding.rule_id,
            db.ValidationFinding.category,
            db.ValidationFinding.severity,
            db.ValidationFinding.concept_id,
        )
        .order_by(db.ValidationFinding.category, db.ValidationFinding.rule_id)
    )
    return [
        {
            "rule": rule,
            "category": category,
            "severity": severity,
            "concept": concept,
            "count": count,
        }
        for rule, category, severity, concept, count in rows
    ]


@router.get("/validation/findings")
def get_validation_findings(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    total = session.scalar(
        select(func.count()).select_from(db.ValidationFinding)
    ) or 0
    rows = session.scalars(
        select(db.ValidationFinding)
        .order_by(db.ValidationFinding.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": row.id,
                "batch": row.ingestion_batch_id,
                "observation": row.observation_id,
                "rule": row.rule_id,
                "category": row.category,
                "severity": row.severity,
                "concept": row.concept_id,
                "invalid_value": row.invalid_value,
                "message": row.message,
            }
            for row in rows
        ],
    }


@router.get("/harmonization/summary")
def get_harmonization_summary(session: Session = Depends(get_db)) -> dict[str, object]:
    batch = session.scalar(
        select(db.HarmonizationBatch)
        .order_by(db.HarmonizationBatch.id.desc())
        .limit(1)
    )
    if batch is None:
        return {
            "source": "UNSD:IMTS(1.2)",
            "target": "AFRSTAT:AFR_TRADE(1.0)",
            "latest_batch": None,
            "rejection_reasons": [],
        }
    reasons = session.execute(
        select(
            db.HarmonizationRejection.reason_code,
            func.count(db.HarmonizationRejection.id),
        )
        .where(db.HarmonizationRejection.harmonization_batch_id == batch.id)
        .group_by(db.HarmonizationRejection.reason_code)
        .order_by(db.HarmonizationRejection.reason_code)
    )
    return {
        "source": "UNSD:IMTS(1.2)",
        "target": "AFRSTAT:AFR_TRADE(1.0)",
        "latest_batch": {
            "id": batch.id,
            "status": _value(batch.status),
            "mapping_definition_id": batch.mapping_definition_id,
            "mapping_version": batch.mapping_version,
            "started_at": batch.started_at,
            "finished_at": batch.finished_at,
            "source_received": batch.source_observations_received,
            "source_valid": batch.source_observations_valid,
            "transformed": batch.observations_transformed,
            "inserted": batch.observations_inserted,
            "updated": batch.observations_updated,
            "skipped": batch.observations_skipped,
            "rejected": batch.observations_rejected,
            "mapping_errors": batch.mapping_errors,
            "target_validation_errors": batch.target_validation_errors,
        },
        "rejection_reasons": [
            {"reason": _value(reason), "count": count}
            for reason, count in reasons
        ],
    }


@router.get("/harmonization/mappings")
def get_harmonization_mappings(
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    rows = session.scalars(
        select(db.SdmxConceptMapping)
        .where(
            db.SdmxConceptMapping.mapping_definition_id
            == "UNSD_IMTS_TO_AFR_TRADE",
            db.SdmxConceptMapping.mapping_version == "1.0",
        )
        .order_by(
            db.SdmxConceptMapping.source_concept_id,
            db.SdmxConceptMapping.target_concept_key,
        )
    )
    return [
        {
            "source_concept": row.source_concept_id,
            "target_concept": row.target_concept_id,
            "mapping_type": _value(row.mapping_type),
            "status": _value(row.status),
            "transformation": row.transformation_id,
            "notes": row.notes,
        }
        for row in rows
    ]


@router.get("/afr-trade/{observation_id}/lineage")
def get_observation_lineage(
    observation_id: int,
    session: Session = Depends(get_db),
) -> dict[str, object]:
    target = session.get(db.AfrTradeObservation, observation_id)
    if target is None:
        raise HTTPException(status_code=404, detail="AFR_TRADE observation not found")
    batch = session.get(db.HarmonizationBatch, target.last_harmonization_batch_id)
    source = session.get(db.TradeObservation, target.source_trade_observation_id)
    ingestion = (
        session.get(db.IngestionBatch, source.last_ingestion_batch_id)
        if source is not None
        else None
    )
    return {
        "target": {
            "id": target.id,
            "dataset": "AFRSTAT:AFR_TRADE(1.0)",
            "key_hash": target.target_key_hash,
            "time_period": target.time_period,
            "obs_value": canonical_decimal(target.obs_value),
        },
        "harmonization_batch": batch.id if batch else None,
        "mapping": {
            "definition": target.mapping_definition_id,
            "version": target.mapping_version,
        },
        "source_observation": {
            "id": source.id if source else None,
            "key_hash": source.source_key_hash if source else None,
            "dimensions": source.source_dimensions if source else None,
        },
        "source_ingestion_batch": ingestion.id if ingestion else None,
        "provider": "UN Statistics Division / UN Comtrade",
    }
