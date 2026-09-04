"""Versioned UNSD IMTS to AFR_TRADE mapping registry tests."""

from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import models as db
from app.mappings.geo import load_source_geo_mappings
from app.mappings.sdmx_mapping_loader import (
    load_mapping_definition,
    load_sdmx_mappings,
    mapping_checksum,
)
from app.mappings.sdmx_mapping_models import (
    MappingStatus,
    MappingType,
    StructureIdentity,
)
from app.mappings.sdmx_mapping_service import (
    get_canonical_geography,
    get_code_mapping,
    get_concept_mapping,
)
from app.pipelines.afr_trade_structure import load_afr_trade_structure
from app.reference.geo import load_geo_reference


SOURCE = StructureIdentity("UNSD", "IMTS", "1.2")
TARGET = StructureIdentity("AFRSTAT", "AFR_TRADE", "1.0")
SOURCE_DIMENSIONS = (
    "FREQ",
    "REF_AREA",
    "TRADE_FLOW",
    "COMMODITY_1",
    "COMMODITY_1_CONF",
    "COMMODITY_2",
    "COMMODITY_2_CONF",
    "COMMODITY_CUSTOM_BREAKDOWN",
    "COUNTERPART_AREA_1",
    "COUNTERPART_AREA_1_CONF",
    "COUNTERPART_AREA_2",
    "COUNTERPART_AREA_2_CONF",
    "TRANSPORT_MODE_BORDER",
    "TRANSPORT_MODE_BORDER_CONF",
    "CUSTOMS_PROC",
    "ACTIVITY",
    "TRANSFORMATION",
    "MEASURE",
    "TIME_PERIOD",
)
SOURCE_ATTRIBUTES = (
    "COMMENT_OBS",
    "COMMODITY_CUSTOM_CODE",
    "COMMODITY_CUSTOM_DESC",
    "COUNTERPART_AREA_1_ANNOTATION",
    "COUNTERPART_AREA_1_TYPE",
    "COUNTERPART_AREA_2_ANNOTATION",
    "COUNTERPART_AREA_2_TYPE",
    "OBS_STATUS",
    "TRADE_SYSTEM",
    "UNIT_MEASURE",
    "UNIT_MULT",
)


def _add_source_codelist(
    session: Session,
    agency: str,
    codelist_id: str,
    version: str,
    codes: tuple[str, ...],
) -> None:
    if session.scalar(
        select(db.Agency).where(db.Agency.agency_id == agency)
    ) is None:
        session.add(db.Agency(agency_id=agency, name=agency))
        session.flush()
    codelist = db.Codelist(
        agency_id=agency,
        codelist_id=codelist_id,
        version=version,
        name=codelist_id,
        source_url="https://fixtures.invalid/structure",
        retrieved_at=datetime.now(timezone.utc),
        checksum="a" * 64,
    )
    session.add(codelist)
    session.flush()
    session.add_all(db.Code(codelist_id=codelist.id, code=code) for code in codes)


def _prepare_structure_registry(session: Session) -> None:
    session.add(db.Agency(agency_id="UNSD", name="UNSD"))
    source_dsd = db.DSD(
        agency_id="UNSD",
        dsd_id="IMTS",
        version="1.2",
        name="IMTS",
        source_url="https://fixtures.invalid/IMTS",
        retrieved_at=datetime.now(timezone.utc),
        checksum="b" * 64,
    )
    session.add(source_dsd)
    session.flush()
    source_dsd.dimensions.extend(
        db.Dimension(concept_id=value, position=index, role="dimension")
        for index, value in enumerate(SOURCE_DIMENSIONS, start=1)
    )
    source_dsd.attributes.extend(
        db.Attribute(concept_id=value, attachment_level="Observation")
        for value in SOURCE_ATTRIBUTES
    )
    source_dsd.measures.append(db.Measure(concept_id="OBS_VALUE"))
    session.commit()

    _add_source_codelist(session, "SDMX", "CL_FREQ", "2.0", ("A", "Q", "M"))
    _add_source_codelist(session, "UNSD", "CL_AREA", "1.0", ("KE", "TN", "W0"))
    _add_source_codelist(session, "UNSD", "CL_TRADE_FLOW", "1.0", ("M", "X"))
    _add_source_codelist(
        session, "UNSD", "CL_COMMODITY", "1.0", ("SITC4_TOTAL",)
    )
    _add_source_codelist(session, "SDMX", "CL_UNIT_MULT", "1.1", ("0",))
    session.commit()
    load_afr_trade_structure(session)


@pytest.fixture
def mapping_session(db_session: Session) -> Session:
    _prepare_structure_registry(db_session)
    load_sdmx_mappings(db_session)
    return db_session


def _concept(
    session: Session, source: str, target: str | None = None
) -> db.SdmxConceptMapping:
    result = get_concept_mapping(
        session,
        SOURCE,
        TARGET,
        source,
        target_concept=target,
        confirmed_only=False,
    )
    assert result.resolved and result.value is not None
    return result.value


def test_mapping_enums_and_definition_identities_are_explicit() -> None:
    definition = load_mapping_definition()

    assert {item.value for item in MappingType} == {
        "DIRECT", "RENAME", "TRANSFORM", "DERIVE", "DROP", "DEFER"
    }
    assert {item.value for item in MappingStatus} == {
        "DRAFT", "CONFIRMED", "MANUAL", "DEPRECATED"
    }
    assert definition.mapping_id == "UNSD_IMTS_TO_AFR_TRADE"
    assert definition.mapping_version == "1.0"
    assert definition.source == SOURCE
    assert definition.target == TARGET


def test_checksum_is_deterministic_and_change_sensitive() -> None:
    first = load_mapping_definition()
    second = load_mapping_definition()
    changed = copy.deepcopy(first.definition)
    changed["mapping"]["version"] = "1.1"

    assert first.checksum == second.checksum
    assert first.checksum == mapping_checksum(first.definition)
    assert mapping_checksum(changed) != first.checksum


def test_loader_is_idempotent_and_stores_checksum(db_session: Session) -> None:
    _prepare_structure_registry(db_session)

    first = load_sdmx_mappings(db_session)
    first_ids = set(db_session.scalars(select(db.SdmxConceptMapping.id)))
    second = load_sdmx_mappings(db_session)
    second_ids = set(db_session.scalars(select(db.SdmxConceptMapping.id)))

    assert (first.action, first.inserted, first.updated, first.unchanged) == (
        "INSERT", 48, 0, 0
    )
    assert (second.action, second.inserted, second.updated, second.unchanged) == (
        "UNCHANGED", 0, 0, 48
    )
    assert (first.transformations, first.concepts, first.codes) == (7, 33, 8)
    assert first.checksum == second.checksum
    assert first_ids == second_ids
    assert set(db_session.scalars(select(db.SdmxConceptMapping.definition_checksum))) == {
        first.checksum
    }


def test_all_source_components_are_classified_and_targets_exist(
    mapping_session: Session,
) -> None:
    rows = list(mapping_session.scalars(select(db.SdmxConceptMapping)))
    source_dsd = mapping_session.scalar(
        select(db.DSD).where(
            db.DSD.agency_id == "UNSD",
            db.DSD.dsd_id == "IMTS",
            db.DSD.version == "1.2",
        )
    )
    target_dsd = mapping_session.scalar(
        select(db.DSD).where(
            db.DSD.agency_id == "AFRSTAT",
            db.DSD.dsd_id == "AFR_TRADE",
            db.DSD.version == "1.0",
        )
    )
    assert source_dsd is not None and target_dsd is not None
    source_ids = {
        *(item.concept_id for item in source_dsd.dimensions),
        *(item.concept_id for item in source_dsd.attributes),
        *(item.concept_id for item in source_dsd.measures),
    }
    source_ids.update(load_mapping_definition().definition["source_metadata_concepts"])
    target_ids = {
        *(item.concept_id for item in target_dsd.dimensions),
        *(item.concept_id for item in target_dsd.attributes),
        *(item.concept_id for item in target_dsd.measures),
    }

    assert source_ids == {row.source_concept_id for row in rows}
    assert all(row.source_concept_id in source_ids for row in rows)
    assert all(
        row.target_concept_id is None or row.target_concept_id in target_ids
        for row in rows
    )
    assert all(
        row.target_concept_id is None
        for row in rows
        if row.mapping_type == MappingType.DROP
    )


@pytest.mark.parametrize(
    ("source", "target", "mapping_type", "status"),
    [
        ("FREQ", "FREQ", MappingType.DIRECT, MappingStatus.CONFIRMED),
        ("REF_AREA", "REF_AREA", MappingType.TRANSFORM, MappingStatus.CONFIRMED),
        ("TRADE_FLOW", "TRADE_FLOW", MappingType.TRANSFORM, MappingStatus.CONFIRMED),
        (
            "COUNTERPART_AREA_1", "COUNTERPART_AREA", MappingType.RENAME,
            MappingStatus.CONFIRMED,
        ),
        ("TIME_PERIOD", "TIME_PERIOD", MappingType.DIRECT, MappingStatus.CONFIRMED),
        (
            "COMMODITY_1", "PRODUCT_SCHEME", MappingType.DERIVE,
            MappingStatus.CONFIRMED,
        ),
        (
            "COMMODITY_1", "PRODUCT", MappingType.DERIVE,
            MappingStatus.CONFIRMED,
        ),
        ("MEASURE", "UNIT_MEASURE", MappingType.DERIVE, MappingStatus.CONFIRMED),
        ("UNIT_MULT", "UNIT_MULT", MappingType.DERIVE, MappingStatus.CONFIRMED),
        ("SOURCE_SYSTEM", "SOURCE", MappingType.DERIVE, MappingStatus.CONFIRMED),
    ],
)
def test_required_concept_mappings(
    mapping_session: Session,
    source: str,
    target: str,
    mapping_type: MappingType,
    status: MappingStatus,
) -> None:
    row = _concept(mapping_session, source, target)
    assert (row.mapping_type, row.status) == (mapping_type, status)


@pytest.mark.parametrize(
    ("source_concept", "target_concept", "source_code", "target_code"),
    [
        ("FREQ", "FREQ", "A", "A"),
        ("REF_AREA", "REF_AREA", "TN", "TN"),
        ("COUNTERPART_AREA_1", "COUNTERPART_AREA", "W0", "AFR_WORLD"),
        ("TRADE_FLOW", "TRADE_FLOW", "M", "IMPORT"),
        ("TRADE_FLOW", "TRADE_FLOW", "X", "EXPORT"),
        ("COMMODITY_1", "PRODUCT_SCHEME", "SITC4_TOTAL", "SITC4"),
        ("COMMODITY_1", "PRODUCT", "SITC4_TOTAL", "TOTAL"),
        ("UNIT_MULT", "UNIT_MULT", "0", "0"),
    ],
)
def test_explicit_mvp_code_mappings(
    mapping_session: Session,
    source_concept: str,
    target_concept: str,
    source_code: str,
    target_code: str,
) -> None:
    concept = _concept(mapping_session, source_concept, target_concept)
    result = get_code_mapping(mapping_session, concept, source_code)

    assert result.resolved and result.value is not None
    assert result.value.target_code == target_code
    assert result.value.status == MappingStatus.CONFIRMED


def test_geography_uses_existing_canonical_bridge(mapping_session: Session) -> None:
    load_geo_reference(mapping_session)
    load_source_geo_mappings(
        mapping_session,
        [
            {
                "PartnerCode": 0,
                "PartnerDesc": "World",
                "PartnerCodeIsoAlpha3": "W00",
                "entryEffectiveDate": "1901-01-01T00:00:00",
                "isGroup": True,
            },
            {
                "PartnerCode": 788,
                "PartnerDesc": "Tunisia",
                "PartnerCodeIsoAlpha2": "TN",
                "PartnerCodeIsoAlpha3": "TUN",
                "entryEffectiveDate": "1900-01-01T00:00:00",
                "isGroup": False,
            },
        ],
    )

    tunisia = get_canonical_geography(
        mapping_session,
        source_agency="UNSD",
        source_system="UN_COMTRADE",
        source_codelist="UNSD:CL_AREA(1.0)",
        source_code="788",
    )
    world = get_canonical_geography(
        mapping_session,
        source_agency="UNSD",
        source_system="UN_COMTRADE",
        source_codelist="UNSD:CL_AREA(1.0)",
        source_code="0",
    )

    assert tunisia.resolved and tunisia.value is not None
    assert (tunisia.value.iso2, tunisia.value.area_type) == ("TN", db.AreaType.COUNTRY)
    assert world.resolved and world.value is not None
    assert world.value.area_type == db.AreaType.AGGREGATE
    assert world.value.iso2 is None


def test_unmapped_product_and_direct_code_fail_safely(
    mapping_session: Session,
) -> None:
    product = _concept(mapping_session, "COMMODITY_1", "PRODUCT")
    frequency = _concept(mapping_session, "FREQ", "FREQ")

    missing_product = get_code_mapping(mapping_session, product, "SITC4_9999")
    missing_frequency = get_code_mapping(mapping_session, frequency, "Q")

    assert (missing_product.resolved, missing_product.value, missing_product.reason) == (
        False, None, "UNRESOLVED_CODE"
    )
    assert (missing_frequency.resolved, missing_frequency.value) == (False, None)


def test_target_version_isolation(mapping_session: Session) -> None:
    result = get_concept_mapping(
        mapping_session,
        SOURCE,
        StructureIdentity("AFRSTAT", "AFR_TRADE", "2.0"),
        "FREQ",
    )

    assert not result.resolved
    assert result.reason == "UNRESOLVED_CONCEPT"


def test_confirmed_only_ignores_draft_and_deprecated(mapping_session: Session) -> None:
    unit = get_concept_mapping(
        mapping_session, SOURCE, TARGET, "MEASURE", target_concept="UNIT_MEASURE"
    )
    frequency = _concept(mapping_session, "FREQ", "FREQ")
    mapping_session.add(
        db.SdmxCodeMapping(
            concept_mapping_id=frequency.id,
            source_codelist_agency="SDMX",
            source_codelist_id="CL_FREQ",
            source_codelist_version="2.0",
            source_code="Q",
            target_codelist_agency="AFRSTAT",
            target_codelist_id="CL_FREQ",
            target_codelist_version="1.0",
            target_code="Q",
            status=MappingStatus.DEPRECATED,
            mapping_method="TEST_ONLY",
            validity_context="OPEN",
        )
    )
    mapping_session.commit()

    deprecated = get_code_mapping(mapping_session, frequency, "Q", confirmed_only=True)
    assert (unit.resolved, unit.reason) == (False, "UNRESOLVED_CONCEPT")
    assert (deprecated.resolved, deprecated.reason) == (False, "UNRESOLVED_CODE")


def test_code_mapping_uniqueness_is_enforced(mapping_session: Session) -> None:
    frequency = _concept(mapping_session, "FREQ", "FREQ")
    mapping_session.add(
        db.SdmxCodeMapping(
            concept_mapping_id=frequency.id,
            source_codelist_agency="SDMX",
            source_codelist_id="CL_FREQ",
            source_codelist_version="2.0",
            source_code="A",
            target_codelist_agency="AFRSTAT",
            target_codelist_id="CL_FREQ",
            target_codelist_version="1.0",
            target_code="A",
            status=MappingStatus.CONFIRMED,
            mapping_method="DUPLICATE_TEST",
            validity_context="OPEN",
        )
    )
    with pytest.raises(IntegrityError):
        mapping_session.commit()
    mapping_session.rollback()


def test_registry_contains_mapping_metadata_only(mapping_session: Session) -> None:
    assert mapping_session.scalar(
        select(func.count()).select_from(db.SdmxConceptMapping)
    ) == 33
    assert mapping_session.scalar(
        select(func.count()).select_from(db.SdmxCodeMapping)
    ) == 8
    assert mapping_session.scalar(select(func.count()).select_from(db.StatDataset)) == 0
    assert mapping_session.scalar(
        select(func.count()).select_from(db.TradeObservation)
    ) == 0
    assert mapping_session.scalar(
        select(func.count()).select_from(db.AfrTradeObservation)
    ) == 0
