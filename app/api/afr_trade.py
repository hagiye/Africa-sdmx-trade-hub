"""Read-only AFR_TRADE statistical REST endpoints (not SDMX REST)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AfrTradeMetadataResponse,
    AfrTradeObservationPage,
    AfrTradeObservationResponse,
)
from app.database import models as db
from app.database.session import get_db
from app.pipelines.afr_trade_structure import load_canonical_structure
from app.pipelines.observation_identity import canonical_decimal


router = APIRouter(prefix="/api/v1/afr-trade", tags=["AFR_TRADE statistics"])


def _response(row: db.AfrTradeObservation) -> AfrTradeObservationResponse:
    return AfrTradeObservationResponse(
        id=row.id,
        FREQ=row.freq,
        REF_AREA=row.ref_area,
        COUNTERPART_AREA=row.counterpart_area,
        TRADE_FLOW=row.trade_flow,
        PRODUCT_SCHEME=row.product_scheme,
        PRODUCT=row.product,
        UNIT_MEASURE=row.unit_measure,
        TIME_PERIOD=row.time_period,
        OBS_VALUE=canonical_decimal(row.obs_value),
        OBS_STATUS=row.obs_status,
        CONF_STATUS=row.conf_status,
        UNIT_MULT=row.unit_mult,
        DECIMALS=row.decimals,
        SOURCE=row.source,
        target_key_hash=row.target_key_hash,
        mapping_definition_id=row.mapping_definition_id,
        mapping_version=row.mapping_version,
    )


@router.get("/metadata", response_model=AfrTradeMetadataResponse)
def get_afr_trade_metadata(
    session: Session = Depends(get_db),
) -> AfrTradeMetadataResponse:
    definition = load_canonical_structure().definition
    dsd = session.scalar(
        select(db.DSD).where(
            db.DSD.agency_id == "AFRSTAT",
            db.DSD.dsd_id == "AFR_TRADE",
            db.DSD.version == "1.0",
        )
    )
    if dsd is None:
        raise HTTPException(status_code=404, detail="AFR_TRADE metadata not loaded")
    codelists = list(
        session.scalars(
            select(db.Codelist)
            .where(db.Codelist.agency_id == "AFRSTAT")
            .order_by(db.Codelist.codelist_id)
        )
    )
    return AfrTradeMetadataResponse(
        agency="AFRSTAT",
        dataflow="AFR_TRADE",
        version="1.0",
        DSD={"agency": "AFRSTAT", "id": "AFR_TRADE", "version": "1.0"},
        dimensions=[row.concept_id for row in dsd.dimensions],
        attributes=[row.concept_id for row in dsd.attributes],
        components=[
            {
                "position": item.get("position"),
                "concept": item["id"],
                "role": item.get("role", "dimension"),
                "codelist": item.get("codelist"),
                "required": item.get("required", False),
            }
            for item in definition["dsd"]["dimensions"]
        ]
        + [
            {
                "position": None,
                "concept": item["id"],
                "role": "attribute",
                "codelist": item.get("codelist"),
                "required": item.get("required", False),
            }
            for item in definition["dsd"]["attributes"]
        ]
        + [
            {
                "position": None,
                "concept": item["id"],
                "role": item.get("role", "measure"),
                "codelist": None,
                "required": True,
            }
            for item in definition["dsd"]["measures"]
        ],
        codelists=[
            {
                "agency": row.agency_id,
                "id": row.codelist_id,
                "version": row.version,
                "code_count": len(row.codes),
            }
            for row in codelists
        ],
        disclaimer=definition["disclaimer"],
    )


@router.get("", response_model=AfrTradeObservationPage)
def list_afr_trade_observations(
    ref_area: str | None = None,
    counterpart_area: str | None = None,
    trade_flow: str | None = None,
    product_scheme: str | None = None,
    product: str | None = None,
    freq: str | None = None,
    start_period: str | None = None,
    end_period: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> AfrTradeObservationPage:
    conditions = []
    for column, value in (
        (db.AfrTradeObservation.ref_area, ref_area),
        (db.AfrTradeObservation.counterpart_area, counterpart_area),
        (db.AfrTradeObservation.trade_flow, trade_flow),
        (db.AfrTradeObservation.product_scheme, product_scheme),
        (db.AfrTradeObservation.product, product),
        (db.AfrTradeObservation.freq, freq),
    ):
        if value is not None:
            conditions.append(column == value)
    if start_period is not None:
        conditions.append(db.AfrTradeObservation.time_period >= start_period)
    if end_period is not None:
        conditions.append(db.AfrTradeObservation.time_period <= end_period)
    total = session.scalar(
        select(func.count()).select_from(db.AfrTradeObservation).where(*conditions)
    ) or 0
    rows = session.scalars(
        select(db.AfrTradeObservation)
        .where(*conditions)
        .order_by(db.AfrTradeObservation.time_period, db.AfrTradeObservation.id)
        .offset(offset)
        .limit(limit)
    )
    return AfrTradeObservationPage(
        items=[_response(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{observation_id}", response_model=AfrTradeObservationResponse)
def get_afr_trade_observation(
    observation_id: int,
    session: Session = Depends(get_db),
) -> AfrTradeObservationResponse:
    row = session.get(db.AfrTradeObservation, observation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="AFR_TRADE observation not found")
    return _response(row)
