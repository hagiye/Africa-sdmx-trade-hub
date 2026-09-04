"""Validation and idempotent persistence for declarative SDMX mappings."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import models as db
from app.mappings.sdmx_mapping_models import MappingDefinition, StructureIdentity
from app.mappings.transformations import is_supported_implementation_key


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAPPING_PATH = ROOT / "mappings" / "unsd_imts_to_afr_trade_1.0.json"


class MappingDefinitionError(ValueError):
    pass


@dataclass(frozen=True)
class MappingLoadResult:
    action: str
    mapping_id: str
    mapping_version: str
    source: StructureIdentity
    target: StructureIdentity
    checksum: str
    transformations: int
    concepts: int
    codes: int
    inserted: int
    updated: int
    unchanged: int


class _ChangeTracker:
    def __init__(self) -> None:
        self.inserted = 0
        self.updated = 0
        self.unchanged = 0

    def record(self, action: str) -> None:
        setattr(self, action, getattr(self, action) + 1)


def _required_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MappingDefinitionError(f"{label} must be an object")
    return value


def _identity(value: object, label: str) -> StructureIdentity:
    item = _required_object(value, label)
    try:
        return StructureIdentity(
            agency=str(item["agency"]),
            structure_id=str(item["structure"]),
            version=str(item["version"]),
        )
    except KeyError as exc:
        raise MappingDefinitionError(f"{label} identity is incomplete") from exc


def _canonical_checksum(definition: dict[str, Any]) -> str:
    payload = json.dumps(
        definition, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def mapping_checksum(definition: dict[str, Any]) -> str:
    """Return the deterministic SHA-256 of a parsed mapping definition."""

    return _canonical_checksum(definition)


def load_mapping_definition(
    path: str | Path = DEFAULT_MAPPING_PATH,
) -> MappingDefinition:
    resolved = Path(path).resolve()
    try:
        definition = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MappingDefinitionError(f"Cannot read mapping definition: {exc}") from exc
    if not isinstance(definition, dict):
        raise MappingDefinitionError("Mapping definition root must be an object")
    if definition.get("format") != "PROJECT_SDMX_MAPPING_DEFINITION":
        raise MappingDefinitionError("Unsupported mapping definition format")
    mapping = _required_object(definition.get("mapping"), "mapping")
    try:
        mapping_id = str(mapping["id"])
        mapping_version = str(mapping["version"])
    except KeyError as exc:
        raise MappingDefinitionError("Mapping identity is incomplete") from exc
    source = _identity(definition.get("source"), "source")
    target = _identity(definition.get("target"), "target")
    transformations = definition.get("transformations")
    concepts = definition.get("concepts")
    codes = definition.get("codes")
    if not all(isinstance(item, list) for item in (transformations, concepts, codes)):
        raise MappingDefinitionError(
            "transformations, concepts, and codes must be arrays"
        )
    source_metadata_concepts = definition.get("source_metadata_concepts", [])
    if (
        not isinstance(source_metadata_concepts, list)
        or any(
            not isinstance(item, str) or not item.strip()
            for item in source_metadata_concepts
        )
        or len(source_metadata_concepts) != len(set(source_metadata_concepts))
    ):
        raise MappingDefinitionError(
            "source_metadata_concepts must be a unique array of non-empty strings"
        )

    transformation_ids: set[str] = set()
    for item in transformations:
        row = _required_object(item, "transformation")
        transformation_id = str(row.get("id", ""))
        implementation_key = str(row.get("implementation_key", ""))
        if not transformation_id or transformation_id in transformation_ids:
            raise MappingDefinitionError(
                f"Duplicate or empty transformation id: {transformation_id!r}"
            )
        if not is_supported_implementation_key(implementation_key):
            raise MappingDefinitionError(
                f"Unsupported implementation key: {implementation_key!r}"
            )
        transformation_ids.add(transformation_id)

    concept_keys: set[tuple[str, str | None]] = set()
    for item in concepts:
        row = _required_object(item, "concept mapping")
        source_concept = str(row.get("source", ""))
        target_concept = row.get("target")
        if target_concept is not None:
            target_concept = str(target_concept)
        key = (source_concept, target_concept)
        if not source_concept or key in concept_keys:
            raise MappingDefinitionError(f"Duplicate or empty concept mapping: {key}")
        concept_keys.add(key)
        try:
            mapping_type = db.SdmxMappingType(str(row["type"]))
            db.SdmxMappingStatus(str(row["status"]))
        except (KeyError, ValueError) as exc:
            raise MappingDefinitionError(f"Invalid concept type/status for {key}") from exc
        if mapping_type == db.SdmxMappingType.DROP and target_concept is not None:
            raise MappingDefinitionError(f"DROP mapping {key} cannot have a target")
        if mapping_type not in {db.SdmxMappingType.DROP, db.SdmxMappingType.DEFER} and not target_concept:
            raise MappingDefinitionError(f"Mapping {key} requires a target")
        transformation_id = row.get("transformation")
        if transformation_id is not None and transformation_id not in transformation_ids:
            raise MappingDefinitionError(
                f"Concept mapping {key} references unknown transformation"
            )

    code_keys: set[tuple[str, str | None, str, str, str, str]] = set()
    for item in codes:
        row = _required_object(item, "code mapping")
        concept = _required_object(row.get("concept"), "code concept")
        source_list = _required_object(row.get("source_codelist"), "source codelist")
        target_list = _required_object(row.get("target_codelist"), "target codelist")
        concept_key = (str(concept.get("source", "")), concept.get("target"))
        if concept_key not in concept_keys:
            raise MappingDefinitionError(
                f"Code mapping references unknown concept mapping: {concept_key}"
            )
        try:
            db.SdmxMappingStatus(str(row["status"]))
            code_key = (
                concept_key[0],
                concept_key[1],
                str(source_list["agency"]),
                str(source_list["id"]),
                str(source_list["version"]),
                str(row["source_code"]),
            )
            for key in ("agency", "id", "version"):
                target_list[key]
            row["target_code"]
            row["method"]
        except (KeyError, ValueError) as exc:
            raise MappingDefinitionError("Incomplete or invalid code mapping") from exc
        if code_key in code_keys:
            raise MappingDefinitionError(f"Duplicate code mapping: {code_key}")
        code_keys.add(code_key)

    return MappingDefinition(
        definition=definition,
        checksum=_canonical_checksum(definition),
        path=resolved,
        mapping_id=mapping_id,
        mapping_version=mapping_version,
        source=source,
        target=target,
    )


def _parse_date(value: object) -> date | None:
    return date.fromisoformat(str(value)) if value else None


def _registry_dsd(session: Session, identity: StructureIdentity) -> db.DSD:
    row = session.scalar(
        select(db.DSD).where(
            db.DSD.agency_id == identity.agency,
            db.DSD.dsd_id == identity.structure_id,
            db.DSD.version == identity.version,
        )
    )
    if row is None:
        raise MappingDefinitionError(
            f"Structure is not loaded in the registry: {identity.display()}"
        )
    return row


def _component_ids(dsd: db.DSD) -> set[str]:
    return {
        *(row.concept_id for row in dsd.dimensions),
        *(row.concept_id for row in dsd.attributes),
        *(row.concept_id for row in dsd.measures),
    }


def _codelist(
    session: Session, identity: dict[str, Any], code: str
) -> db.Codelist:
    row = session.scalar(
        select(db.Codelist).where(
            db.Codelist.agency_id == str(identity["agency"]),
            db.Codelist.codelist_id == str(identity["id"]),
            db.Codelist.version == str(identity["version"]),
        )
    )
    if row is None:
        raise MappingDefinitionError(
            f"Codelist is not loaded: {identity['agency']}:{identity['id']}({identity['version']})"
        )
    if not any(item.code == code for item in row.codes):
        raise MappingDefinitionError(
            f"Code {code!r} is absent from {identity['agency']}:{identity['id']}({identity['version']})"
        )
    return row


def _apply(row: object, values: dict[str, object]) -> str:
    changed = any(getattr(row, key) != value for key, value in values.items())
    if not changed:
        return "unchanged"
    for key, value in values.items():
        setattr(row, key, value)
    return "updated"


def load_sdmx_mappings(
    session: Session,
    path: str | Path = DEFAULT_MAPPING_PATH,
) -> MappingLoadResult:
    """Validate registry references and idempotently load mapping metadata."""

    mapping = load_mapping_definition(path)
    definition = mapping.definition
    source_dsd = _registry_dsd(session, mapping.source)
    target_dsd = _registry_dsd(session, mapping.target)
    source_concepts = _component_ids(source_dsd) | set(
        definition.get("source_metadata_concepts", [])
    )
    target_concepts = _component_ids(target_dsd)
    for item in definition["concepts"]:
        if item["source"] not in source_concepts:
            raise MappingDefinitionError(
                f"Source concept is absent from {mapping.source.display()}: {item['source']}"
            )
        if item["target"] is not None and item["target"] not in target_concepts:
            raise MappingDefinitionError(
                f"Target concept is absent from {mapping.target.display()}: {item['target']}"
            )
    for item in definition["codes"]:
        _codelist(session, item["source_codelist"], str(item["source_code"]))
        _codelist(session, item["target_codelist"], str(item["target_code"]))

    tracker = _ChangeTracker()
    try:
        for item in definition["transformations"]:
            row = session.scalar(
                select(db.SdmxTransformationDefinition).where(
                    db.SdmxTransformationDefinition.transformation_id == item["id"],
                    db.SdmxTransformationDefinition.version == item["version"],
                )
            )
            values = {
                "name": item["name"],
                "description": item["description"],
                "implementation_key": item["implementation_key"],
            }
            if row is None:
                session.add(
                    db.SdmxTransformationDefinition(
                        transformation_id=item["id"],
                        version=item["version"],
                        **values,
                    )
                )
                tracker.record("inserted")
            else:
                tracker.record(_apply(row, values))
        session.flush()

        concept_rows: dict[tuple[str, str | None], db.SdmxConceptMapping] = {}
        for item in definition["concepts"]:
            target_concept = item["target"]
            row = session.scalar(
                select(db.SdmxConceptMapping).where(
                    db.SdmxConceptMapping.mapping_definition_id == mapping.mapping_id,
                    db.SdmxConceptMapping.mapping_version == mapping.mapping_version,
                    db.SdmxConceptMapping.source_agency == mapping.source.agency,
                    db.SdmxConceptMapping.source_structure_id == mapping.source.structure_id,
                    db.SdmxConceptMapping.source_structure_version == mapping.source.version,
                    db.SdmxConceptMapping.source_concept_id == item["source"],
                    db.SdmxConceptMapping.target_agency == mapping.target.agency,
                    db.SdmxConceptMapping.target_structure_id == mapping.target.structure_id,
                    db.SdmxConceptMapping.target_structure_version == mapping.target.version,
                    db.SdmxConceptMapping.target_concept_key
                    == (target_concept or ""),
                )
            )
            values = {
                "definition_checksum": mapping.checksum,
                "target_concept_id": target_concept,
                "target_concept_key": target_concept or "",
                "mapping_type": db.SdmxMappingType(item["type"]),
                "status": db.SdmxMappingStatus(item["status"]),
                "transformation_id": item.get("transformation"),
                "valid_from": _parse_date(item.get("valid_from")),
                "valid_to": _parse_date(item.get("valid_to")),
                "notes": item.get("notes"),
            }
            if row is None:
                row = db.SdmxConceptMapping(
                    mapping_definition_id=mapping.mapping_id,
                    mapping_version=mapping.mapping_version,
                    source_agency=mapping.source.agency,
                    source_structure_id=mapping.source.structure_id,
                    source_structure_version=mapping.source.version,
                    source_concept_id=item["source"],
                    target_agency=mapping.target.agency,
                    target_structure_id=mapping.target.structure_id,
                    target_structure_version=mapping.target.version,
                    **values,
                )
                session.add(row)
                tracker.record("inserted")
            else:
                tracker.record(_apply(row, values))
            session.flush()
            concept_rows[(item["source"], target_concept)] = row

        for item in definition["codes"]:
            concept_key = (item["concept"]["source"], item["concept"]["target"])
            concept_row = concept_rows[concept_key]
            valid_from = _parse_date(item.get("valid_from"))
            valid_to = _parse_date(item.get("valid_to"))
            validity_context = f"{valid_from or ''}/{valid_to or ''}" or "OPEN"
            if validity_context == "/":
                validity_context = "OPEN"
            source_list = item["source_codelist"]
            target_list = item["target_codelist"]
            row = session.scalar(
                select(db.SdmxCodeMapping).where(
                    db.SdmxCodeMapping.concept_mapping_id == concept_row.id,
                    db.SdmxCodeMapping.source_codelist_agency == source_list["agency"],
                    db.SdmxCodeMapping.source_codelist_id == source_list["id"],
                    db.SdmxCodeMapping.source_codelist_version == source_list["version"],
                    db.SdmxCodeMapping.source_code == item["source_code"],
                    db.SdmxCodeMapping.validity_context == validity_context,
                )
            )
            values = {
                "target_codelist_agency": target_list["agency"],
                "target_codelist_id": target_list["id"],
                "target_codelist_version": target_list["version"],
                "target_code": item["target_code"],
                "status": db.SdmxMappingStatus(item["status"]),
                "mapping_method": item["method"],
                "valid_from": valid_from,
                "valid_to": valid_to,
                "notes": item.get("notes"),
            }
            if row is None:
                session.add(
                    db.SdmxCodeMapping(
                        concept_mapping_id=concept_row.id,
                        source_codelist_agency=source_list["agency"],
                        source_codelist_id=source_list["id"],
                        source_codelist_version=source_list["version"],
                        source_code=item["source_code"],
                        validity_context=validity_context,
                        **values,
                    )
                )
                tracker.record("inserted")
            else:
                tracker.record(_apply(row, values))
        session.commit()
    except Exception:
        session.rollback()
        raise

    action = "INSERT" if tracker.inserted else "UPDATE" if tracker.updated else "UNCHANGED"
    return MappingLoadResult(
        action=action,
        mapping_id=mapping.mapping_id,
        mapping_version=mapping.mapping_version,
        source=mapping.source,
        target=mapping.target,
        checksum=mapping.checksum,
        transformations=len(definition["transformations"]),
        concepts=len(definition["concepts"]),
        codes=len(definition["codes"]),
        inserted=tracker.inserted,
        updated=tracker.updated,
        unchanged=tracker.unchanged,
    )
