"""Idempotently prepare a small, deterministic recruiter-facing demo database.

This script never calls UN Comtrade or an SDMX service. It uses the checked-in
SDMX DSD snapshot, canonical metadata, and controlled 2022–2024 fixtures. The
2023 payload intentionally repeats its one record so the database includes a
real, non-rejecting duplicate-quality validation result for the demo UI.
Run ``alembic upgrade head`` before invoking it.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import func, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import models as db
from app.database.session import SessionLocal
from app.harmonization.harmonization_pipeline import harmonize_source_warehouse
from app.mappings.geo import load_source_geo_mappings
from app.mappings.sdmx_mapping_loader import load_sdmx_mappings
from app.pipelines.afr_trade_structure import load_afr_trade_structure
from app.pipelines.ingest_trade_data import TradeQuery, ingest_trade_query
from app.reference.geo import load_geo_reference
from app.sdmx.parser import parse_dsd
from scripts.seed_stat_dataset import seed_stat_dataset


SOURCE_DSD_PATH = ROOT / "structures" / "raw" / "UNSD_datastructure_IMTS_1.2.xml"
FIXTURE_DIRECTORY = ROOT / "tests" / "fixtures" / "data"
PERIODS = ("2022", "2023", "2024")
DEMO_QUERY = TradeQuery(
    type_code="C",
    frequency_code="A",
    classification_code="S4",
    periods=PERIODS,
    reporter_code="788",
    flow_code="M",
    partner_code="0",
    partner2_code="0",
    commodity_code="TOTAL",
)
SOURCE_CODELISTS = (
    ("SDMX", "CL_FREQ", "2.0", "Frequency", ("A", "Q", "M")),
    ("UNSD", "CL_AREA", "1.0", "Area", ("W0", "KE", "TN")),
    ("UNSD", "CL_TRADE_FLOW", "1.0", "Trade flow", ("M", "X")),
    ("UNSD", "CL_COMMODITY", "1.0", "Commodity", ("SITC4_TOTAL",)),
    ("SDMX", "CL_UNIT_MULT", "1.1", "Unit multiplier", ("0",)),
)
PROVIDER_AREAS = (
    {
        "PartnerCode": 0,
        "PartnerDesc": "World",
        "PartnerCodeIsoAlpha3": "W00",
        "entryEffectiveDate": "1901-01-01T00:00:00",
        "isGroup": True,
    },
    {
        "PartnerCode": 404,
        "PartnerDesc": "Kenya",
        "PartnerCodeIsoAlpha2": "KE",
        "PartnerCodeIsoAlpha3": "KEN",
        "entryEffectiveDate": "1900-01-01T00:00:00",
        "isGroup": False,
    },
    {
        "PartnerCode": 788,
        "PartnerDesc": "Tunisia",
        "PartnerCodeIsoAlpha2": "TN",
        "PartnerCodeIsoAlpha3": "TUN",
        "entryEffectiveDate": "1900-01-01T00:00:00",
        "isGroup": False,
    },
)


@dataclass(frozen=True)
class BootstrapResult:
    source_metadata: str
    geography: str
    target_structure: str
    mappings: str
    ingestion: str
    harmonization: str
    counts: dict[str, int]


def verify_migrations_current(session: Session) -> None:
    """Fail clearly when the connected database is not at the Alembic head."""
    config = Config(str(ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    expected = set(scripts.get_heads())
    current = set(MigrationContext.configure(session.connection()).get_current_heads())
    if current != expected:
        raise RuntimeError(
            "Database migrations are not current. Run 'alembic upgrade head' "
            f"before bootstrap (current={sorted(current)}, expected={sorted(expected)})."
        )


def _ensure_agency(session: Session, agency_id: str, name: str | None = None) -> db.Agency:
    row = session.scalar(select(db.Agency).where(db.Agency.agency_id == agency_id))
    if row is None:
        row = db.Agency(agency_id=agency_id, name=name or agency_id)
        session.add(row)
        session.flush()
    return row


def _ensure_source_codelists(session: Session, loaded_at: datetime) -> None:
    for agency, codelist_id, version, name, codes in SOURCE_CODELISTS:
        _ensure_agency(session, agency)
        row = session.scalar(
            select(db.Codelist).where(
                db.Codelist.agency_id == agency,
                db.Codelist.codelist_id == codelist_id,
                db.Codelist.version == version,
            )
        )
        if row is None:
            row = db.Codelist(
                agency_id=agency,
                codelist_id=codelist_id,
                version=version,
                name=name,
                source_url=f"internal:demo-source-metadata/{agency}/{codelist_id}/{version}",
                retrieved_at=loaded_at,
                checksum=hashlib.sha256("\n".join(codes).encode()).hexdigest(),
            )
            session.add(row)
            session.flush()
        present = set(session.scalars(select(db.Code.code).where(db.Code.codelist_id == row.id)))
        session.add_all(db.Code(codelist_id=row.id, code=code) for code in codes if code not in present)


def load_demo_source_metadata(session: Session) -> str:
    """Load the real checked-in IMTS DSD plus the bounded code subset used by the demo."""
    payload = SOURCE_DSD_PATH.read_bytes()
    parsed = parse_dsd(payload)
    checksum = hashlib.sha256(payload).hexdigest()
    loaded_at = datetime.now(timezone.utc)
    _ensure_agency(session, "UNSD", "United Nations Statistics Division")
    _ensure_agency(session, "SDMX", "SDMX")
    _ensure_source_codelists(session, loaded_at)

    dsd = session.scalar(
        select(db.DSD).where(
            db.DSD.agency_id == parsed.agency,
            db.DSD.dsd_id == parsed.structure_id,
            db.DSD.version == parsed.version,
        )
    )
    action = "UNCHANGED"
    if dsd is None:
        dsd = db.DSD(
            agency_id=parsed.agency,
            dsd_id=parsed.structure_id,
            version=parsed.version,
            name=parsed.labels.get("en", parsed.structure_id),
            source_url="internal:structures/raw/UNSD_datastructure_IMTS_1.2.xml",
            retrieved_at=loaded_at,
            checksum=checksum,
        )
        session.add(dsd)
        session.flush()
        action = "INSERTED"
    elif dsd.checksum != checksum:
        dsd.dimensions.clear()
        dsd.attributes.clear()
        dsd.measures.clear()
        session.flush()
        dsd.name = parsed.labels.get("en", parsed.structure_id)
        dsd.retrieved_at = loaded_at
        dsd.checksum = checksum
        action = "UPDATED"

    if action != "UNCHANGED":
        for component in parsed.dimensions:
            reference = component.codelist
            dsd.dimensions.append(
                db.Dimension(
                    concept_id=component.concept_id,
                    position=component.position or 999,
                    role=component.role,
                    representation=component.representation,
                    codelist_agency_id=reference.agency if reference else None,
                    codelist_id=reference.structure_id if reference else None,
                    codelist_version=reference.version if reference else None,
                )
            )
        for component in parsed.attributes:
            reference = component.codelist
            dsd.attributes.append(
                db.Attribute(
                    concept_id=component.concept_id,
                    attachment_level=component.attachment_level,
                    representation=component.representation,
                    codelist_agency_id=reference.agency if reference else None,
                    codelist_id=reference.structure_id if reference else None,
                    codelist_version=reference.version if reference else None,
                )
            )
        dsd.measures.extend(
            db.Measure(concept_id=item.concept_id, representation=item.representation)
            for item in parsed.measures
        )

    scheme = session.scalar(
        select(db.ConceptScheme).where(
            db.ConceptScheme.agency_id == "UNSD",
            db.ConceptScheme.scheme_id == "CS_IMTS",
            db.ConceptScheme.version == "1.0",
        )
    )
    if scheme is None:
        scheme = db.ConceptScheme(
            agency_id="UNSD",
            scheme_id="CS_IMTS",
            version="1.0",
            name="IMTS concepts (controlled demo subset)",
            source_url="internal:structures/raw/UNSD_datastructure_IMTS_1.2.xml",
            retrieved_at=loaded_at,
            checksum=checksum,
        )
        session.add(scheme)
        session.flush()
    present_concepts = {item.concept_id for item in scheme.concepts}
    component_ids = {
        item.concept_id for item in (*parsed.dimensions, *parsed.attributes, *parsed.measures)
    }
    session.add_all(
        db.Concept(concept_scheme_id=scheme.id, concept_id=concept_id, name=concept_id)
        for concept_id in sorted(component_ids - present_concepts)
    )

    flow = session.scalar(
        select(db.Dataflow).where(
            db.Dataflow.agency_id == "UNSD",
            db.Dataflow.dataflow_id == "IMTS_A",
            db.Dataflow.version == "1.0",
        )
    )
    if flow is None:
        flow = db.Dataflow(
            agency_id="UNSD",
            dataflow_id="IMTS_A",
            version="1.0",
            name="International Merchandise Trade Statistics — Annual",
            source_url="internal:demo-source-metadata/UNSD/IMTS_A/1.0",
            retrieved_at=loaded_at,
            checksum=checksum,
            dsd_agency_id="UNSD",
            dsd_id="IMTS",
            dsd_version="1.2",
        )
        session.add(flow)
    session.commit()
    return action


def _fixture(period: str, _parameters: dict[str, str]) -> dict[str, object]:
    path = FIXTURE_DIRECTORY / f"un_comtrade_tunisia_imports_world_{period}.json"
    payload = copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))
    if period == "2023":
        records = payload.get("data")
        if not isinstance(records, list) or len(records) != 1:
            raise RuntimeError("The controlled 2023 fixture must contain one record")
        records.append(copy.deepcopy(records[0]))
        payload["count"] = len(records)
    return payload


def _counts(session: Session) -> dict[str, int]:
    models = {
        "agencies": db.Agency,
        "dataflows": db.Dataflow,
        "dsds": db.DSD,
        "concepts": db.Concept,
        "codelists": db.Codelist,
        "codes": db.Code,
        "geographies": db.GeoArea,
        "source_geo_mappings": db.SourceGeoMapping,
        "concept_mappings": db.SdmxConceptMapping,
        "code_mappings": db.SdmxCodeMapping,
        "source_observations": db.TradeObservation,
        "validation_results": db.ValidationFinding,
        "target_observations": db.AfrTradeObservation,
        "lineage_rows": db.AfrTradeObservation,
    }
    return {
        name: session.scalar(select(func.count()).select_from(model)) or 0
        for name, model in models.items()
    }


def bootstrap_demo_database(
    session: Session, *, verify_migrations: bool = True
) -> BootstrapResult:
    if verify_migrations:
        verify_migrations_current(session)

    source_metadata = load_demo_source_metadata(session)
    geography_result = load_geo_reference(session)
    geography = (
        "UNCHANGED" if not geography_result.inserted and not geography_result.updated else "LOADED"
    )
    source_geo = load_source_geo_mappings(session, PROVIDER_AREAS)
    if source_geo.unmapped:
        raise RuntimeError("Controlled demo geography contains an unmapped source code")
    target = load_afr_trade_structure(session)
    mappings = load_sdmx_mappings(session)
    dataset = seed_stat_dataset(session)

    source_count = session.scalar(
        select(func.count()).select_from(db.TradeObservation).where(
            db.TradeObservation.dataset_id == dataset.dataset_id
        )
    ) or 0
    if source_count < len(PERIODS):
        ingestion_batch = ingest_trade_query(
            session,
            dataset_id=dataset.dataset_id,
            query=DEMO_QUERY,
            fetch_response=_fixture,
        )
        ingestion = ingestion_batch.status.value
    else:
        ingestion = "UNCHANGED"

    target_count = session.scalar(select(func.count()).select_from(db.AfrTradeObservation)) or 0
    if target_count < len(PERIODS):
        harmonization_batch = harmonize_source_warehouse(
            session, source_dataset_id=dataset.dataset_id
        )
        harmonization = harmonization_batch.status.value
    else:
        harmonization = "UNCHANGED"

    result = BootstrapResult(
        source_metadata=source_metadata,
        geography=geography,
        target_structure=target.action,
        mappings=mappings.action,
        ingestion=ingestion,
        harmonization=harmonization,
        counts=_counts(session),
    )
    if result.counts["source_observations"] < len(PERIODS):
        raise RuntimeError("Demo bootstrap did not create all controlled source observations")
    if result.counts["target_observations"] < len(PERIODS):
        raise RuntimeError("Demo bootstrap did not create all AFR_TRADE observations")
    if result.counts["validation_results"] < 1:
        raise RuntimeError("Demo bootstrap did not create validation evidence")
    return result


def main() -> int:
    with SessionLocal() as session:
        result = bootstrap_demo_database(session)
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
