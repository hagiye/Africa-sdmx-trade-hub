"""Read-only metadata lookup service for SDMX concept and code mappings."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.database import models as db
from app.mappings.sdmx_mapping_models import LookupResult, StructureIdentity


def _valid_on(model: type, effective_on: date | None) -> tuple:
    day = effective_on or date.today()
    return (
        (model.valid_from.is_(None) | (model.valid_from <= day)),
        (model.valid_to.is_(None) | (model.valid_to >= day)),
    )


def _concept_query(
    source: StructureIdentity,
    target: StructureIdentity,
    source_concept: str,
    *,
    target_concept: str | None,
    mapping_definition_id: str | None,
    mapping_version: str | None,
    confirmed_only: bool,
    effective_on: date | None,
) -> Select:
    model = db.SdmxConceptMapping
    query = select(model).where(
        model.source_agency == source.agency,
        model.source_structure_id == source.structure_id,
        model.source_structure_version == source.version,
        model.target_agency == target.agency,
        model.target_structure_id == target.structure_id,
        model.target_structure_version == target.version,
        model.source_concept_id == source_concept,
        *_valid_on(model, effective_on),
    )
    if target_concept is not None:
        query = query.where(model.target_concept_id == target_concept)
    if mapping_definition_id is not None:
        query = query.where(model.mapping_definition_id == mapping_definition_id)
    if mapping_version is not None:
        query = query.where(model.mapping_version == mapping_version)
    if confirmed_only:
        query = query.where(model.status == db.SdmxMappingStatus.CONFIRMED)
    else:
        query = query.where(model.status != db.SdmxMappingStatus.DEPRECATED)
    return query.order_by(model.id)


def get_concept_mappings(
    session: Session,
    source: StructureIdentity,
    target: StructureIdentity,
    source_concept: str,
    *,
    target_concept: str | None = None,
    mapping_definition_id: str | None = None,
    mapping_version: str | None = None,
    confirmed_only: bool = True,
    effective_on: date | None = None,
) -> list[db.SdmxConceptMapping]:
    """Return all eligible targets (a source concept may derive several)."""

    return list(
        session.scalars(
            _concept_query(
                source,
                target,
                source_concept,
                target_concept=target_concept,
                mapping_definition_id=mapping_definition_id,
                mapping_version=mapping_version,
                confirmed_only=confirmed_only,
                effective_on=effective_on,
            )
        )
    )


def get_concept_mapping(
    session: Session,
    source: StructureIdentity,
    target: StructureIdentity,
    source_concept: str,
    *,
    target_concept: str | None = None,
    mapping_definition_id: str | None = None,
    mapping_version: str | None = None,
    confirmed_only: bool = True,
    effective_on: date | None = None,
) -> LookupResult[db.SdmxConceptMapping]:
    """Resolve one concept mapping or return an explicit failure reason."""

    rows = get_concept_mappings(
        session,
        source,
        target,
        source_concept,
        target_concept=target_concept,
        mapping_definition_id=mapping_definition_id,
        mapping_version=mapping_version,
        confirmed_only=confirmed_only,
        effective_on=effective_on,
    )
    if not rows:
        return LookupResult(resolved=False, reason="UNRESOLVED_CONCEPT")
    if len(rows) > 1:
        return LookupResult(resolved=False, reason="MULTIPLE_TARGET_CONCEPTS")
    return LookupResult(resolved=True, value=rows[0])


def get_code_mapping(
    session: Session,
    concept_mapping: db.SdmxConceptMapping,
    source_code: str,
    *,
    confirmed_only: bool = True,
    effective_on: date | None = None,
) -> LookupResult[db.SdmxCodeMapping]:
    """Resolve an explicit code mapping; never return ``source_code`` as fallback."""

    if confirmed_only and concept_mapping.status != db.SdmxMappingStatus.CONFIRMED:
        return LookupResult(resolved=False, reason="CONCEPT_MAPPING_NOT_CONFIRMED")
    model = db.SdmxCodeMapping
    query = select(model).where(
        model.concept_mapping_id == concept_mapping.id,
        model.source_code == source_code,
        *_valid_on(model, effective_on),
    )
    if confirmed_only:
        query = query.where(model.status == db.SdmxMappingStatus.CONFIRMED)
    else:
        query = query.where(model.status != db.SdmxMappingStatus.DEPRECATED)
    rows = list(session.scalars(query.order_by(model.id)))
    if not rows:
        return LookupResult(resolved=False, reason="UNRESOLVED_CODE")
    if len(rows) > 1:
        return LookupResult(resolved=False, reason="AMBIGUOUS_CODE_MAPPING")
    if rows[0].target_code is None:
        return LookupResult(resolved=False, value=rows[0], reason="TARGET_CODE_DEFERRED")
    return LookupResult(resolved=True, value=rows[0])


def get_canonical_geography(
    session: Session,
    *,
    source_agency: str,
    source_system: str,
    source_codelist: str,
    source_code: str,
    confirmed_only: bool = True,
) -> LookupResult[db.GeoArea]:
    """Resolve geography through the existing authoritative bridge."""

    query = select(db.SourceGeoMapping).where(
        db.SourceGeoMapping.source_agency == source_agency,
        db.SourceGeoMapping.source_system == source_system,
        db.SourceGeoMapping.source_codelist == source_codelist,
        db.SourceGeoMapping.source_code == source_code,
    )
    if confirmed_only:
        query = query.where(
            db.SourceGeoMapping.mapping_status == db.MappingStatus.CONFIRMED
        )
    row = session.scalar(query)
    if row is None or row.geo_area is None:
        return LookupResult(resolved=False, reason="UNRESOLVED_GEOGRAPHY")
    return LookupResult(resolved=True, value=row.geo_area)
