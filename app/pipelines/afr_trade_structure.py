"""Load the internal AFR_TRADE canonical definition into the SDMX registry."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import models as db
from app.pipelines.observation_identity import canonical_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = ROOT / "structures" / "afr_trade" / "afr_trade_1.0.json"
EXPECTED_DISCLAIMER = (
    "AFRSTAT:AFR_TRADE is an independent portfolio demonstration structure "
    "and is not an official African Union or STATAFRIC SDMX artefact."
)


class AFRTradeStructureError(ValueError):
    """The checked-in canonical structure is incomplete or inconsistent."""


@dataclass(frozen=True)
class CanonicalStructure:
    definition: dict[str, Any]
    checksum: str
    path: Path


@dataclass(frozen=True)
class StructureLoadResult:
    action: str
    checksum: str
    inserted: int
    updated: int
    unchanged: int
    concepts: int
    dimensions: int
    attributes: int
    measures: int
    codelists: int
    codes: int


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AFRTradeStructureError(
            f"Cannot read canonical AFR_TRADE definition {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise AFRTradeStructureError("Canonical AFR_TRADE definition must be an object")
    return value


def _canonical_geography_codes(source: dict[str, Any]) -> list[dict[str, Any]]:
    relative = Path(str(source.get("path", "")))
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise AFRTradeStructureError("Geography source must remain inside the repository") from exc
    geography = _read_json(path)
    rows = geography.get("areas")
    if not isinstance(rows, list):
        raise AFRTradeStructureError("Canonical geography source has no areas list")
    codes = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("area_type") != "COUNTRY"
            or row.get("au_member") is not True
        ):
            continue
        code = row.get(source.get("code_field", "iso2"))
        if not code:
            raise AFRTradeStructureError("AU country has no requested target code")
        codes.append(
            {
                "id": str(code),
                "labels": {"en": row["name_en"], "fr": row["name_fr"]},
                "annotations": {
                    "area_type": "COUNTRY",
                    "is_iso_country": True,
                    "iso2": row["iso2"],
                    "iso3": row["iso3"],
                },
            }
        )
    return sorted(codes, key=lambda item: item["id"])


def _expand_code_sources(definition: dict[str, Any]) -> dict[str, Any]:
    expanded = copy.deepcopy(definition)
    for codelist in expanded.get("codelists", []):
        source = codelist.pop("codes_from", None)
        if source is None:
            continue
        if source.get("type") != "canonical_au_member_geography":
            raise AFRTradeStructureError(
                f"Unsupported code source for {codelist.get('id')!r}"
            )
        derived = _canonical_geography_codes(source)
        codelist["codes"] = sorted(
            [*derived, *codelist.get("codes", [])], key=lambda item: item["id"]
        )
    return expanded


def _require_labels(item: dict[str, Any], identity: str) -> None:
    labels = item.get("labels")
    if not isinstance(labels, dict) or not labels.get("en") or not labels.get("fr"):
        raise AFRTradeStructureError(f"{identity} requires English and French labels")


def _validate_definition(definition: dict[str, Any]) -> None:
    if definition.get("format") != "AFRSTAT_CANONICAL_STRUCTURE_JSON":
        raise AFRTradeStructureError("Unexpected canonical structure format")
    if definition.get("is_sdmx_ml") is not False:
        raise AFRTradeStructureError("Internal JSON must not claim to be SDMX-ML")
    if definition.get("disclaimer") != EXPECTED_DISCLAIMER:
        raise AFRTradeStructureError("Required non-official disclaimer is missing")
    agency = definition.get("agency", {})
    dataflow = definition.get("dataflow", {})
    dsd = definition.get("dsd", {})
    scheme = definition.get("concept_scheme", {})
    if agency.get("id") != "AFRSTAT":
        raise AFRTradeStructureError("Target agency must be AFRSTAT")
    if dataflow.get("id") != "AFR_TRADE" or dsd.get("id") != "AFR_TRADE":
        raise AFRTradeStructureError("Target dataflow and DSD must be AFR_TRADE")
    if any(
        item.get("version") != "1.0" for item in (dataflow, dsd, scheme)
    ):
        raise AFRTradeStructureError("All target structures must use version 1.0")
    for identity, item in (
        ("agency", agency),
        ("dataflow", dataflow),
        ("DSD", dsd),
        ("concept scheme", scheme),
    ):
        _require_labels(item, identity)

    concepts = scheme.get("concepts", [])
    concept_ids = [item.get("id") for item in concepts]
    if len(concept_ids) != len(set(concept_ids)):
        raise AFRTradeStructureError("Target concept IDs must be unique")
    for concept in concepts:
        _require_labels(concept, f"concept {concept.get('id')}")

    dimensions = dsd.get("dimensions", [])
    positions = [item.get("position") for item in dimensions]
    if positions != list(range(1, len(dimensions) + 1)):
        raise AFRTradeStructureError("Target dimension positions must be contiguous")
    components = [*dimensions, *dsd.get("attributes", []), *dsd.get("measures", [])]
    missing_concepts = {item.get("id") for item in components} - set(concept_ids)
    if missing_concepts:
        raise AFRTradeStructureError(
            f"DSD components lack concepts: {sorted(missing_concepts)}"
        )
    measures = dsd.get("measures", [])
    if len(measures) != 1 or measures[0].get("id") != "OBS_VALUE":
        raise AFRTradeStructureError("OBS_VALUE must be the sole primary measure")

    codelists = definition.get("codelists", [])
    identities = {
        ("AFRSTAT", item.get("id"), item.get("version")) for item in codelists
    }
    if len(identities) != len(codelists):
        raise AFRTradeStructureError("Target codelist identities must be unique")
    for codelist in codelists:
        _require_labels(codelist, f"codelist {codelist.get('id')}")
        codes = codelist.get("codes", [])
        code_ids = [item.get("id") for item in codes]
        if len(code_ids) != len(set(code_ids)):
            raise AFRTradeStructureError(
                f"Codes in {codelist.get('id')} must be unique"
            )
        for code in codes:
            _require_labels(code, f"code {codelist.get('id')}:{code.get('id')}")
    for component in components:
        reference = component.get("codelist")
        if reference is None:
            continue
        identity = (reference["agency"], reference["id"], reference["version"])
        if identity not in identities:
            raise AFRTradeStructureError(
                f"Codelist reference does not resolve: {identity}"
            )


def load_canonical_structure(
    path: Path = DEFAULT_MODEL_PATH,
) -> CanonicalStructure:
    """Read, expand, validate, and checksum the version-controlled definition."""
    resolved_path = path.resolve()
    definition = _expand_code_sources(_read_json(resolved_path))
    _validate_definition(definition)
    checksum = hashlib.sha256(
        canonical_json(definition).encode("utf-8")
    ).hexdigest()
    return CanonicalStructure(definition=definition, checksum=checksum, path=resolved_path)


def structure_checksum(definition: dict[str, Any]) -> str:
    """Return a deterministic checksum for a resolved canonical definition."""
    return hashlib.sha256(canonical_json(definition).encode("utf-8")).hexdigest()


def _replace_labels(
    session: Session,
    entity_type: str,
    entity_pk: int,
    labels: dict[str, str],
) -> None:
    session.execute(
        delete(db.LocalizedLabel).where(
            db.LocalizedLabel.entity_type == entity_type,
            db.LocalizedLabel.entity_pk == entity_pk,
        )
    )
    session.add_all(
        db.LocalizedLabel(
            entity_type=entity_type,
            entity_pk=entity_pk,
            language=language,
            label=label,
        )
        for language, label in sorted(labels.items())
    )


@dataclass
class _Tracker:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    def record(self, action: str) -> None:
        setattr(self, action, getattr(self, action) + 1)


def _checksum_action(row: object | None, checksum: str) -> str:
    if row is None:
        return "inserted"
    return "unchanged" if getattr(row, "checksum") == checksum else "updated"


def _source_url(path: Path) -> str:
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        relative = path
    return f"internal:{relative.as_posix()}"


def load_afr_trade_structure(
    session: Session,
    path: Path = DEFAULT_MODEL_PATH,
) -> StructureLoadResult:
    """Idempotently load AFR_TRADE into the shared metadata registry."""
    canonical = load_canonical_structure(path)
    model = canonical.definition
    checksum = canonical.checksum
    loaded_at = datetime.now(timezone.utc)
    source_url = _source_url(canonical.path)
    tracker = _Tracker()

    try:
        agency_data = model["agency"]
        agency = session.scalar(
            select(db.Agency).where(db.Agency.agency_id == agency_data["id"])
        )
        if agency is None:
            agency = db.Agency(
                agency_id=agency_data["id"], name=agency_data["labels"]["en"]
            )
            session.add(agency)
            session.flush()
            agency_action = "inserted"
        elif agency.name != agency_data["labels"]["en"]:
            agency.name = agency_data["labels"]["en"]
            agency_action = "updated"
        else:
            agency_action = "unchanged"
        tracker.record(agency_action)
        if agency_action != "unchanged":
            _replace_labels(session, "agency", agency.id, agency_data["labels"])

        for codelist_data in model["codelists"]:
            codelist = session.scalar(
                select(db.Codelist).where(
                    db.Codelist.agency_id == agency.agency_id,
                    db.Codelist.codelist_id == codelist_data["id"],
                    db.Codelist.version == codelist_data["version"],
                )
            )
            action = _checksum_action(codelist, checksum)
            tracker.record(action)
            if action == "unchanged":
                continue
            if codelist is None:
                codelist = db.Codelist(
                    agency_id=agency.agency_id,
                    codelist_id=codelist_data["id"],
                    version=codelist_data["version"],
                    name=codelist_data["labels"]["en"],
                    source_url=source_url,
                    retrieved_at=loaded_at,
                    checksum=checksum,
                )
                session.add(codelist)
                session.flush()
            else:
                code_ids = [code.id for code in codelist.codes]
                if code_ids:
                    session.execute(
                        delete(db.LocalizedLabel).where(
                            db.LocalizedLabel.entity_type == "code",
                            db.LocalizedLabel.entity_pk.in_(code_ids),
                        )
                    )
                codelist.codes.clear()
                session.flush()
            codelist.name = codelist_data["labels"]["en"]
            codelist.source_url = source_url
            codelist.retrieved_at = loaded_at
            codelist.checksum = checksum
            _replace_labels(session, "codelist", codelist.id, codelist_data["labels"])
            for code_data in codelist_data["codes"]:
                code = db.Code(codelist_id=codelist.id, code=code_data["id"])
                session.add(code)
                session.flush()
                _replace_labels(session, "code", code.id, code_data["labels"])

        scheme_data = model["concept_scheme"]
        scheme = session.scalar(
            select(db.ConceptScheme).where(
                db.ConceptScheme.agency_id == agency.agency_id,
                db.ConceptScheme.scheme_id == scheme_data["id"],
                db.ConceptScheme.version == scheme_data["version"],
            )
        )
        action = _checksum_action(scheme, checksum)
        tracker.record(action)
        if action != "unchanged":
            if scheme is None:
                scheme = db.ConceptScheme(
                    agency_id=agency.agency_id,
                    scheme_id=scheme_data["id"],
                    version=scheme_data["version"],
                    name=scheme_data["labels"]["en"],
                    source_url=source_url,
                    retrieved_at=loaded_at,
                    checksum=checksum,
                )
                session.add(scheme)
                session.flush()
            else:
                concept_ids = [concept.id for concept in scheme.concepts]
                if concept_ids:
                    session.execute(
                        delete(db.LocalizedLabel).where(
                            db.LocalizedLabel.entity_type == "concept",
                            db.LocalizedLabel.entity_pk.in_(concept_ids),
                        )
                    )
                scheme.concepts.clear()
                session.flush()
            scheme.name = scheme_data["labels"]["en"]
            scheme.source_url = source_url
            scheme.retrieved_at = loaded_at
            scheme.checksum = checksum
            _replace_labels(session, "concept_scheme", scheme.id, scheme_data["labels"])
            for concept_data in scheme_data["concepts"]:
                concept = db.Concept(
                    concept_scheme_id=scheme.id,
                    concept_id=concept_data["id"],
                    name=concept_data["labels"]["en"],
                    description=concept_data.get("description"),
                )
                session.add(concept)
                session.flush()
                _replace_labels(session, "concept", concept.id, concept_data["labels"])

        dsd_data = model["dsd"]
        dsd = session.scalar(
            select(db.DSD).where(
                db.DSD.agency_id == agency.agency_id,
                db.DSD.dsd_id == dsd_data["id"],
                db.DSD.version == dsd_data["version"],
            )
        )
        action = _checksum_action(dsd, checksum)
        tracker.record(action)
        if action != "unchanged":
            if dsd is None:
                dsd = db.DSD(
                    agency_id=agency.agency_id,
                    dsd_id=dsd_data["id"],
                    version=dsd_data["version"],
                    name=dsd_data["labels"]["en"],
                    source_url=source_url,
                    retrieved_at=loaded_at,
                    checksum=checksum,
                )
                session.add(dsd)
                session.flush()
            else:
                dsd.dimensions.clear()
                dsd.attributes.clear()
                dsd.measures.clear()
                session.flush()
            dsd.name = dsd_data["labels"]["en"]
            dsd.source_url = source_url
            dsd.retrieved_at = loaded_at
            dsd.checksum = checksum
            _replace_labels(session, "dsd", dsd.id, dsd_data["labels"])
            for component in dsd_data["dimensions"]:
                reference = component.get("codelist") or {}
                dsd.dimensions.append(
                    db.Dimension(
                        concept_id=component["id"],
                        position=component["position"],
                        role=component["role"],
                        representation=component.get("representation"),
                        codelist_agency_id=reference.get("agency"),
                        codelist_id=reference.get("id"),
                        codelist_version=reference.get("version"),
                    )
                )
            for component in dsd_data["attributes"]:
                reference = component.get("codelist") or {}
                dsd.attributes.append(
                    db.Attribute(
                        concept_id=component["id"],
                        attachment_level=component["attachment_level"],
                        representation=component.get("representation"),
                        codelist_agency_id=reference.get("agency"),
                        codelist_id=reference.get("id"),
                        codelist_version=reference.get("version"),
                    )
                )
            dsd.measures.extend(
                db.Measure(
                    concept_id=component["id"],
                    representation=component.get("representation"),
                )
                for component in dsd_data["measures"]
            )

        dataflow_data = model["dataflow"]
        dataflow = session.scalar(
            select(db.Dataflow).where(
                db.Dataflow.agency_id == agency.agency_id,
                db.Dataflow.dataflow_id == dataflow_data["id"],
                db.Dataflow.version == dataflow_data["version"],
            )
        )
        action = _checksum_action(dataflow, checksum)
        tracker.record(action)
        if action != "unchanged":
            if dataflow is None:
                dataflow = db.Dataflow(
                    agency_id=agency.agency_id,
                    dataflow_id=dataflow_data["id"],
                    version=dataflow_data["version"],
                    name=dataflow_data["labels"]["en"],
                    source_url=source_url,
                    retrieved_at=loaded_at,
                    checksum=checksum,
                )
                session.add(dataflow)
                session.flush()
            dataflow.name = dataflow_data["labels"]["en"]
            dataflow.description = model["disclaimer"]
            dataflow.is_external_reference = False
            dataflow.source_url = source_url
            dataflow.retrieved_at = loaded_at
            dataflow.checksum = checksum
            dataflow.dsd_agency_id = dataflow_data["dsd_ref"]["agency"]
            dataflow.dsd_id = dataflow_data["dsd_ref"]["id"]
            dataflow.dsd_version = dataflow_data["dsd_ref"]["version"]
            _replace_labels(session, "dataflow", dataflow.id, dataflow_data["labels"])

        session.commit()
    except Exception:
        session.rollback()
        raise

    action = "INSERT" if tracker.inserted else "UPDATE" if tracker.updated else "UNCHANGED"
    return StructureLoadResult(
        action=action,
        checksum=checksum,
        inserted=tracker.inserted,
        updated=tracker.updated,
        unchanged=tracker.unchanged,
        concepts=len(model["concept_scheme"]["concepts"]),
        dimensions=len(model["dsd"]["dimensions"]),
        attributes=len(model["dsd"]["attributes"]),
        measures=len(model["dsd"]["measures"]),
        codelists=len(model["codelists"]),
        codes=sum(len(item["codes"]) for item in model["codelists"]),
    )
