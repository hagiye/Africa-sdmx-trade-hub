"""Read-only SDMX metadata registry API."""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    CodePage,
    CodeResponse,
    CodelistResponse,
    ComponentResponse,
    DSDResponse,
    DataflowResponse,
)
from app.database import models as db
from app.database.session import get_db

router = APIRouter(prefix="/api/v1", tags=["SDMX metadata"])


def _labels(session: Session, entity_type: str, entity_pk: int) -> dict[str, str]:
    rows = session.execute(
        select(db.LocalizedLabel.language, db.LocalizedLabel.label).where(
            db.LocalizedLabel.entity_type == entity_type,
            db.LocalizedLabel.entity_pk == entity_pk,
        )
    )
    return dict(rows.tuples().all())


def _codelist(component) -> dict[str, str] | None:
    if not component.codelist_id:
        return None
    return {
        "agency": component.codelist_agency_id,
        "id": component.codelist_id,
        "version": component.codelist_version,
    }


def _dataflow(session: Session, row: db.Dataflow) -> DataflowResponse:
    reference = None
    if row.dsd_id:
        reference = {
            "agency": row.dsd_agency_id,
            "id": row.dsd_id,
            "version": row.dsd_version,
        }
    return DataflowResponse(
        agency=row.agency_id,
        id=row.dataflow_id,
        version=row.version,
        name=row.name,
        description=row.description,
        labels=_labels(session, "dataflow", row.id),
        dsd=reference,
    )


def _component(row, *, role: str | None = None) -> ComponentResponse:
    return ComponentResponse(
        concept=row.concept_id,
        role=getattr(row, "role", role),
        position=getattr(row, "position", None),
        attachment_level=getattr(row, "attachment_level", None),
        representation=row.representation,
        codelist=_codelist(row) if hasattr(row, "codelist_id") else None,
    )


def _dsd(session: Session, row: db.DSD) -> DSDResponse:
    return DSDResponse(
        agency=row.agency_id,
        id=row.dsd_id,
        version=row.version,
        name=row.name,
        labels=_labels(session, "dsd", row.id),
        dimensions=[_component(item) for item in row.dimensions],
        attributes=[_component(item, role="attribute") for item in row.attributes],
        measures=[_component(item, role="measure") for item in row.measures],
    )


def _find_dsd(session: Session, agency: str, dsd_id: str, version: str) -> db.DSD:
    row = session.scalar(
        select(db.DSD).where(
            db.DSD.agency_id == agency,
            db.DSD.dsd_id == dsd_id,
            db.DSD.version == version,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="DSD not found")
    return row


def _find_codelist(
    session: Session, agency: str, codelist_id: str, version: str
) -> db.Codelist:
    row = session.scalar(
        select(db.Codelist).where(
            db.Codelist.agency_id == agency,
            db.Codelist.codelist_id == codelist_id,
            db.Codelist.version == version,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Codelist not found")
    return row


@router.get("/dataflows", response_model=list[DataflowResponse])
def list_dataflows(session: Session = Depends(get_db)) -> list[DataflowResponse]:
    rows = session.scalars(
        select(db.Dataflow).order_by(db.Dataflow.agency_id, db.Dataflow.dataflow_id)
    )
    return [_dataflow(session, row) for row in rows]


@router.get("/dataflows/{agency}/{dataflow_id}/{version}", response_model=DataflowResponse)
def get_dataflow(
    agency: str, dataflow_id: str, version: str, session: Session = Depends(get_db)
) -> DataflowResponse:
    row = session.scalar(
        select(db.Dataflow).where(
            db.Dataflow.agency_id == agency,
            db.Dataflow.dataflow_id == dataflow_id,
            db.Dataflow.version == version,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Dataflow not found")
    return _dataflow(session, row)


@router.get("/dsd/{agency}/{dsd_id}/{version}", response_model=DSDResponse)
def get_dsd(
    agency: str, dsd_id: str, version: str, session: Session = Depends(get_db)
) -> DSDResponse:
    return _dsd(session, _find_dsd(session, agency, dsd_id, version))


@router.get(
    "/dsd/{agency}/{dsd_id}/{version}/dimensions",
    response_model=list[ComponentResponse],
)
def get_dimensions(
    agency: str, dsd_id: str, version: str, session: Session = Depends(get_db)
) -> list[ComponentResponse]:
    return [_component(item) for item in _find_dsd(session, agency, dsd_id, version).dimensions]


def _codelist_response(session: Session, row: db.Codelist) -> CodelistResponse:
    count = session.scalar(
        select(func.count()).select_from(db.Code).where(db.Code.codelist_id == row.id)
    )
    return CodelistResponse(
        agency=row.agency_id,
        id=row.codelist_id,
        version=row.version,
        name=row.name,
        labels=_labels(session, "codelist", row.id),
        code_count=count or 0,
    )


@router.get("/codelists", response_model=list[CodelistResponse])
def list_codelists(session: Session = Depends(get_db)) -> list[CodelistResponse]:
    rows = session.scalars(
        select(db.Codelist).order_by(db.Codelist.agency_id, db.Codelist.codelist_id)
    )
    return [_codelist_response(session, row) for row in rows]


@router.get(
    "/codelists/{agency}/{codelist_id}/{version}", response_model=CodelistResponse
)
def get_codelist(
    agency: str, codelist_id: str, version: str, session: Session = Depends(get_db)
) -> CodelistResponse:
    return _codelist_response(
        session, _find_codelist(session, agency, codelist_id, version)
    )


@router.get(
    "/codelists/{agency}/{codelist_id}/{version}/codes", response_model=CodePage
)
def get_codes(
    agency: str,
    codelist_id: str,
    version: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_db),
) -> CodePage:
    codelist = _find_codelist(session, agency, codelist_id, version)
    total = session.scalar(
        select(func.count()).select_from(db.Code).where(db.Code.codelist_id == codelist.id)
    ) or 0
    rows = session.scalars(
        select(db.Code)
        .where(db.Code.codelist_id == codelist.id)
        .order_by(db.Code.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        CodeResponse(
            code=row.code,
            parent_code=row.parent_code,
            labels=_labels(session, "code", row.id),
        )
        for row in rows
    ]
    return CodePage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=math.ceil(total / page_size) if total else 0,
    )
