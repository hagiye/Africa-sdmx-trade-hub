"""Retrieve and idempotently persist the selected trade structure graph."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import models as db
from app.sdmx.client import SDMXClient, SDMXResponse
from app.sdmx.discovery import (
    PROVIDER_BASE_URL,
    PROVIDER_NAME,
    TRADE_DATAFLOW,
    SDMXDiscovery,
)
from app.sdmx.models import Codelist, ConceptScheme, Dataflow, DataStructure, Labels
from app.sdmx.exceptions import SDMXStructureNotFound

LOGGER = logging.getLogger(__name__)


@dataclass
class ImportSummary:
    provider: str = PROVIDER_NAME
    dataflow: str = ""
    dsd: str = ""
    version: str = ""
    concept_schemes: int = 0
    concepts: int = 0
    codelists: int = 0
    codes: int = 0
    dimensions: int = 0
    attributes: int = 0
    measures: int = 0
    constraints: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    checksum_changes: int = 0
    status: str = "RUNNING"
    constraints_note: str = "Constraint discovery not attempted."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _display(labels: Labels, fallback: str) -> str:
    return labels.get("en") or next(iter(labels.values()), fallback)


def _description(labels: Labels) -> str | None:
    return labels.get("en") or next(iter(labels.values()), None)


def _agency(session: Session, agency_id: str) -> None:
    if session.scalar(select(db.Agency).where(db.Agency.agency_id == agency_id)) is None:
        session.add(db.Agency(agency_id=agency_id, name=agency_id))
        session.flush()


def _replace_labels(
    session: Session, entity_type: str, entity_pk: int, labels: Labels
) -> None:
    session.execute(
        delete(db.LocalizedLabel).where(
            db.LocalizedLabel.entity_type == entity_type,
            db.LocalizedLabel.entity_pk == entity_pk,
        )
    )
    _add_labels(session, entity_type, entity_pk, labels)


def _add_labels(
    session: Session, entity_type: str, entity_pk: int, labels: Labels
) -> None:
    session.add_all(
        db.LocalizedLabel(
            entity_type=entity_type,
            entity_pk=entity_pk,
            language=language,
            label=label,
        )
        for language, label in labels.items()
    )


def _action(existing_checksum: str | None, response: SDMXResponse) -> str:
    if existing_checksum is None:
        return "insert"
    return "unchanged" if existing_checksum == response.checksum else "update"


def _record_action(summary: ImportSummary, action: str, identity: str) -> None:
    if action == "insert":
        summary.inserted += 1
    elif action == "update":
        summary.updated += 1
        summary.checksum_changes += 1
    else:
        summary.unchanged += 1
    LOGGER.info("SDMX database action=%s identity=%s", action, identity)


def _persist_dataflow(
    session: Session,
    item: Dataflow,
    response: SDMXResponse,
    summary: ImportSummary,
) -> None:
    _agency(session, item.agency)
    row = session.scalar(
        select(db.Dataflow).where(
            db.Dataflow.agency_id == item.agency,
            db.Dataflow.dataflow_id == item.structure_id,
            db.Dataflow.version == item.version,
        )
    )
    action = _action(row.checksum if row else None, response)
    _record_action(summary, action, f"dataflow:{item.agency}:{item.structure_id}({item.version})")
    if action == "unchanged":
        return
    if row is None:
        row = db.Dataflow(
            agency_id=item.agency,
            dataflow_id=item.structure_id,
            version=item.version,
            name="",
            source_url=response.url,
            retrieved_at=_now(),
            checksum=response.checksum,
        )
        session.add(row)
    row.name = _display(item.labels, item.structure_id)
    row.description = _description(item.descriptions)
    row.is_external_reference = item.is_external_reference
    row.source_url = response.url
    row.retrieved_at = _now()
    row.checksum = response.checksum
    if item.structure:
        row.dsd_agency_id = item.structure.agency
        row.dsd_id = item.structure.structure_id
        row.dsd_version = item.structure.version
    session.flush()
    _replace_labels(session, "dataflow", row.id, item.labels)


def _component_codelist(component) -> tuple[str | None, str | None, str | None]:
    if not component.codelist:
        return None, None, None
    return (
        component.codelist.agency,
        component.codelist.structure_id,
        component.codelist.version,
    )


def _persist_dsd(
    session: Session,
    item: DataStructure,
    response: SDMXResponse,
    summary: ImportSummary,
) -> db.DSD:
    _agency(session, item.agency)
    row = session.scalar(
        select(db.DSD).where(
            db.DSD.agency_id == item.agency,
            db.DSD.dsd_id == item.structure_id,
            db.DSD.version == item.version,
        )
    )
    action = _action(row.checksum if row else None, response)
    _record_action(summary, action, f"dsd:{item.agency}:{item.structure_id}({item.version})")
    if action == "unchanged":
        return row
    if row is None:
        row = db.DSD(
            agency_id=item.agency,
            dsd_id=item.structure_id,
            version=item.version,
            name="",
            source_url=response.url,
            retrieved_at=_now(),
            checksum=response.checksum,
        )
        session.add(row)
    else:
        row.dimensions.clear()
        row.attributes.clear()
        row.measures.clear()
        session.flush()
    row.name = _display(item.labels, item.structure_id)
    row.source_url = response.url
    row.retrieved_at = _now()
    row.checksum = response.checksum
    session.flush()
    _replace_labels(session, "dsd", row.id, item.labels)
    next_position = max((component.position or 0 for component in item.dimensions), default=0)
    for component in item.dimensions:
        position = component.position
        if position is None:
            next_position += 1
            position = next_position
        agency, codelist_id, version = _component_codelist(component)
        row.dimensions.append(
            db.Dimension(
                concept_id=component.concept_id,
                position=position,
                role=component.role,
                representation=component.representation,
                codelist_agency_id=agency,
                codelist_id=codelist_id,
                codelist_version=version,
            )
        )
    for component in item.attributes:
        agency, codelist_id, version = _component_codelist(component)
        row.attributes.append(
            db.Attribute(
                concept_id=component.concept_id,
                attachment_level=component.attachment_level,
                representation=component.representation,
                codelist_agency_id=agency,
                codelist_id=codelist_id,
                codelist_version=version,
            )
        )
    row.measures.extend(
        db.Measure(concept_id=item.concept_id, representation=item.representation)
        for item in item.measures
    )
    summary.inserted += len(item.dimensions) + len(item.attributes) + len(item.measures)
    return row


def _delete_child_labels(session: Session, entity_type: str, ids: list[int]) -> None:
    if ids:
        session.execute(
            delete(db.LocalizedLabel).where(
                db.LocalizedLabel.entity_type == entity_type,
                db.LocalizedLabel.entity_pk.in_(ids),
            )
        )


def _persist_concept_scheme(
    session: Session,
    item: ConceptScheme,
    response: SDMXResponse,
    summary: ImportSummary,
) -> None:
    _agency(session, item.agency)
    row = session.scalar(
        select(db.ConceptScheme).where(
            db.ConceptScheme.agency_id == item.agency,
            db.ConceptScheme.scheme_id == item.structure_id,
            db.ConceptScheme.version == item.version,
        )
    )
    action = _action(row.checksum if row else None, response)
    _record_action(summary, action, f"conceptscheme:{item.agency}:{item.structure_id}({item.version})")
    if action == "unchanged":
        return
    if row is None:
        row = db.ConceptScheme(
            agency_id=item.agency,
            scheme_id=item.structure_id,
            version=item.version,
            name="",
            source_url=response.url,
            retrieved_at=_now(),
            checksum=response.checksum,
        )
        session.add(row)
    else:
        _delete_child_labels(session, "concept", [child.id for child in row.concepts])
        row.concepts.clear()
        session.flush()
    row.name = _display(item.labels, item.structure_id)
    row.source_url = response.url
    row.retrieved_at = _now()
    row.checksum = response.checksum
    session.flush()
    _replace_labels(session, "concept_scheme", row.id, item.labels)
    concept_rows = []
    for concept in item.concepts:
        child = db.Concept(
            concept_id=concept.concept_id,
            name=_display(concept.labels, concept.concept_id),
            description=_description(concept.descriptions),
        )
        row.concepts.append(child)
        concept_rows.append((child, concept.labels))
    session.flush()
    for child, labels in concept_rows:
        _add_labels(session, "concept", child.id, labels)
    summary.inserted += len(item.concepts)


def _persist_codelist(
    session: Session,
    item: Codelist,
    response: SDMXResponse,
    summary: ImportSummary,
) -> None:
    _agency(session, item.agency)
    row = session.scalar(
        select(db.Codelist).where(
            db.Codelist.agency_id == item.agency,
            db.Codelist.codelist_id == item.structure_id,
            db.Codelist.version == item.version,
        )
    )
    action = _action(row.checksum if row else None, response)
    _record_action(summary, action, f"codelist:{item.agency}:{item.structure_id}({item.version})")
    if action == "unchanged":
        return
    if row is None:
        row = db.Codelist(
            agency_id=item.agency,
            codelist_id=item.structure_id,
            version=item.version,
            name="",
            source_url=response.url,
            retrieved_at=_now(),
            checksum=response.checksum,
        )
        session.add(row)
    else:
        _delete_child_labels(session, "code", [child.id for child in row.codes])
        row.codes.clear()
        session.flush()
    row.name = _display(item.labels, item.structure_id)
    row.source_url = response.url
    row.retrieved_at = _now()
    row.checksum = response.checksum
    session.flush()
    _replace_labels(session, "codelist", row.id, item.labels)
    code_rows = []
    for code in item.codes:
        child = db.Code(code=code.code, parent_code=code.parent_code)
        row.codes.append(child)
        code_rows.append((child, code.labels))
    session.flush()
    for child, labels in code_rows:
        _add_labels(session, "code", child.id, labels)
    summary.inserted += len(item.codes)


def import_structures(session: Session, client: SDMXClient | None = None) -> ImportSummary:
    """Import the selected dataflow, DSD, and exactly referenced item schemes."""
    client = client or SDMXClient(PROVIDER_BASE_URL)
    discovery = SDMXDiscovery(client)
    summary = ImportSummary()
    batch = db.StructureImport(
        provider=PROVIDER_NAME,
        started_at=_now(),
        status="RUNNING",
    )
    session.add(batch)
    session.commit()
    try:
        flows, flow_response = discovery.get_dataflows(
            TRADE_DATAFLOW.agency, TRADE_DATAFLOW.structure_id, TRADE_DATAFLOW.version
        )
        flow = next(
            item
            for item in flows
            if (item.agency, item.structure_id, item.version)
            == (TRADE_DATAFLOW.agency, TRADE_DATAFLOW.structure_id, TRADE_DATAFLOW.version)
        )
        if flow.structure is None:
            raise ValueError("Selected dataflow does not reference a DSD")
        dsd, dsd_response = discovery.get_dsd(flow.structure)
        summary.dataflow = f"{flow.agency}:{flow.structure_id}({flow.version})"
        summary.dsd = f"{dsd.agency}:{dsd.structure_id}"
        summary.version = dsd.version
        summary.dimensions = len(dsd.dimensions)
        summary.attributes = len(dsd.attributes)
        summary.measures = len(dsd.measures)
        summary.concept_schemes = len(dsd.concept_schemes)
        summary.codelists = len(dsd.codelists)
        _persist_dataflow(session, flow, flow_response, summary)
        _persist_dsd(session, dsd, dsd_response, summary)
        received = 2
        for ref in sorted(dsd.concept_schemes, key=lambda value: (value.agency, value.structure_id, value.version)):
            scheme, response = discovery.get_concept_scheme(ref)
            summary.concepts += len(scheme.concepts)
            _persist_concept_scheme(session, scheme, response, summary)
            received += 1
        for ref in sorted(dsd.codelists, key=lambda value: (value.agency, value.structure_id, value.version)):
            codelist, response = discovery.get_codelist(ref)
            summary.codes += len(codelist.codes)
            _persist_codelist(session, codelist, response, summary)
            received += 1
        try:
            constraints, _ = discovery.get_constraints(TRADE_DATAFLOW.agency)
            summary.constraints = len(constraints)
            received += len(constraints)
            summary.constraints_note = (
                f"{len(constraints)} data constraint(s) published for "
                f"agency {TRADE_DATAFLOW.agency}."
            )
        except SDMXStructureNotFound:
            summary.constraints_note = (
                f"No data constraints are published for agency "
                f"{TRADE_DATAFLOW.agency} at the provider endpoint."
            )
        batch = session.get(db.StructureImport, batch.id)
        batch.finished_at = _now()
        batch.status = "SUCCESS"
        batch.structures_received = received
        batch.structures_inserted = summary.inserted
        batch.structures_updated = summary.updated
        batch.checksum_changes = summary.checksum_changes
        summary.status = "SUCCESS"
        session.commit()
        return summary
    except Exception as exc:
        session.rollback()
        batch = session.get(db.StructureImport, batch.id)
        batch.finished_at = _now()
        batch.status = "FAILED"
        batch.error_message = str(exc)[:4000]
        session.commit()
        LOGGER.exception("SDMX structure import failed")
        raise
