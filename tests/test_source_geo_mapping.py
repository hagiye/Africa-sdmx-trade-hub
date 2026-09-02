"""Offline source geography mapping model, loader, and service tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import (
    Agency,
    AreaType,
    Code,
    Codelist,
    GeoArea,
    MappingStatus,
    SourceGeoMapping,
)
from app.mappings.geo import (
    CODELIST_IDENTITY,
    SOURCE_AGENCY,
    SOURCE_CODELIST,
    SOURCE_SYSTEM,
    is_au_reporter,
    load_source_geo_mappings,
    resolve_source_area,
    resolve_source_mapping,
)
from app.reference.geo import load_geo_reference


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "data"
    / "un_comtrade_tunisia_imports_world_2022.json"
)

# Synthetic subset shaped exactly like the official partnerAreas.json records.
SYNTHETIC_PROVIDER_RECORDS = [
    {
        "PartnerCode": 0,
        "PartnerDesc": "World",
        "partnerNote": "World",
        "PartnerCodeIsoAlpha3": "W00",
        "entryEffectiveDate": "1901-01-01T00:00:00",
        "isGroup": True,
    },
    {
        "PartnerCode": 404,
        "PartnerDesc": "Kenya",
        "partnerNote": "Kenya",
        "PartnerCodeIsoAlpha2": "KE",
        "PartnerCodeIsoAlpha3": "KEN",
        "entryEffectiveDate": "1900-01-01T00:00:00",
        "isGroup": False,
    },
    {
        "PartnerCode": 788,
        "PartnerDesc": "Tunisia",
        "partnerNote": "Tunisia",
        "PartnerCodeIsoAlpha2": "TN",
        "PartnerCodeIsoAlpha3": "TUN",
        "entryEffectiveDate": "1900-01-01T00:00:00",
        "isGroup": False,
    },
    {
        "PartnerCode": 800,
        "PartnerDesc": "Uganda",
        "partnerNote": "Uganda",
        "PartnerCodeIsoAlpha2": "UG",
        "PartnerCodeIsoAlpha3": "UGA",
        "entryEffectiveDate": "1900-01-01T00:00:00",
        "isGroup": False,
    },
    {
        "PartnerCode": 999999,
        "PartnerDesc": "Synthetic unresolved area",
        "partnerNote": "Synthetic test only",
        "isGroup": False,
    },
]


def _prepare_reference_database(session: Session) -> None:
    load_geo_reference(session)
    agency, codelist_id, version = CODELIST_IDENTITY
    session.add(Agency(agency_id=agency, name="United Nations Statistics Division"))
    codelist = Codelist(
        agency_id=agency,
        codelist_id=codelist_id,
        version=version,
        name="CL_AREA",
        source_url="https://fixtures.invalid/CL_AREA",
        retrieved_at=datetime.now(timezone.utc),
        checksum="a" * 64,
    )
    session.add(codelist)
    session.flush()
    session.add_all(
        [Code(codelist_id=codelist.id, code=code) for code in ("W0", "KE", "TN")]
    )
    session.commit()


@pytest.fixture
def mapped_session(db_session: Session) -> Session:
    _prepare_reference_database(db_session)
    load_source_geo_mappings(db_session, SYNTHETIC_PROVIDER_RECORDS)
    return db_session


def test_mapping_model_and_status_values_exist() -> None:
    assert SourceGeoMapping.__tablename__ == "source_geo_mapping"
    assert {status.value for status in MappingStatus} == {
        "CONFIRMED",
        "AUTO_MATCHED",
        "MANUAL",
        "UNMAPPED",
    }


@pytest.mark.parametrize(
    ("source_code", "name", "iso2", "iso3"),
    [("788", "Tunisia", "TN", "TUN"), ("404", "Kenya", "KE", "KEN")],
)
def test_required_au_country_mappings(
    mapped_session: Session,
    source_code: str,
    name: str,
    iso2: str,
    iso3: str,
) -> None:
    area = resolve_source_area(
        mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, source_code
    )
    mapping = resolve_source_mapping(
        mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, source_code
    )

    assert area is not None
    assert (area.name_en, area.iso2, area.iso3) == (name, iso2, iso3)
    assert area.area_type is AreaType.COUNTRY
    assert area.au_member is True
    assert mapping is not None and mapping.mapping_status is MappingStatus.CONFIRMED


def test_world_maps_to_one_identifier_free_aggregate(mapped_session: Session) -> None:
    world = resolve_source_area(mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, "0")

    assert world is not None
    assert world.name_en == "World"
    assert world.name_fr == "Monde"
    assert world.area_type is AreaType.AGGREGATE
    assert world.au_member is False
    assert (world.iso2, world.iso3, world.numeric_code) == (None, None, None)
    assert mapped_session.scalar(
        select(func.count()).select_from(GeoArea).where(GeoArea.name_en == "World")
    ) == 1
    assert mapped_session.scalar(
        select(func.count())
        .select_from(GeoArea)
        .where(GeoArea.area_type == AreaType.COUNTRY)
    ) == 55


def test_reporter_eligibility_and_safe_unknown_resolution(
    mapped_session: Session,
) -> None:
    assert is_au_reporter(mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, "788") is True
    assert is_au_reporter(mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, "404") is True
    assert is_au_reporter(mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, "0") is False
    assert resolve_source_area(
        mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, "999999"
    ) is None
    assert resolve_source_area(
        mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, "123456"
    ) is None
    unresolved = resolve_source_mapping(
        mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, "999999"
    )
    assert unresolved is not None
    assert unresolved.mapping_status is MappingStatus.UNMAPPED


def test_exact_current_iso_match_is_auto_matched(mapped_session: Session) -> None:
    mapping = resolve_source_mapping(
        mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, "800"
    )

    assert mapping is not None
    assert mapping.mapping_status is MappingStatus.AUTO_MATCHED
    assert mapping.mapping_method == "ISO_NUMERIC_EXACT"
    assert mapping.geo_area is not None and mapping.geo_area.iso2 == "UG"


def test_manual_override_survives_mapping_reload(mapped_session: Session) -> None:
    mapping = resolve_source_mapping(
        mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, "999999"
    )
    uganda = mapped_session.scalar(select(GeoArea).where(GeoArea.iso2 == "UG"))
    assert mapping is not None and uganda is not None
    mapping.geo_area_id = uganda.id
    mapping.mapping_status = MappingStatus.MANUAL
    mapping.mapping_method = "REVIEWED_TEST_OVERRIDE"
    mapped_session.commit()

    load_source_geo_mappings(mapped_session, SYNTHETIC_PROVIDER_RECORDS)
    reloaded = resolve_source_mapping(
        mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, "999999"
    )

    assert reloaded is not None
    assert reloaded.geo_area_id == uganda.id
    assert reloaded.mapping_status is MappingStatus.MANUAL
    assert reloaded.mapping_method == "REVIEWED_TEST_OVERRIDE"


def test_mapping_identity_uniqueness_is_enforced(mapped_session: Session) -> None:
    existing = resolve_source_mapping(
        mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, "788"
    )
    assert existing is not None
    mapped_session.add(
        SourceGeoMapping(
            source_agency=SOURCE_AGENCY,
            source_system=SOURCE_SYSTEM,
            source_codelist=SOURCE_CODELIST,
            source_code="788",
            geo_area_id=existing.geo_area_id,
            mapping_status=MappingStatus.CONFIRMED,
        )
    )
    with pytest.raises(IntegrityError):
        mapped_session.commit()
    mapped_session.rollback()


def test_mapping_loader_is_idempotent(db_session: Session) -> None:
    _prepare_reference_database(db_session)

    first = load_source_geo_mappings(db_session, SYNTHETIC_PROVIDER_RECORDS)
    first_ids = set(db_session.scalars(select(SourceGeoMapping.id)))
    second = load_source_geo_mappings(db_session, SYNTHETIC_PROVIDER_RECORDS)
    second_ids = set(db_session.scalars(select(SourceGeoMapping.id)))

    assert (
        first.source_codes_examined,
        first.inserted,
        first.updated,
        first.unchanged,
        first.mapped,
        first.unmapped,
        first.total_mappings,
    ) == (5, 5, 0, 0, 4, 1, 5)
    assert first.world_created is True
    assert (
        second.source_codes_examined,
        second.inserted,
        second.updated,
        second.unchanged,
        second.mapped,
        second.unmapped,
        second.total_mappings,
    ) == (5, 0, 0, 5, 4, 1, 5)
    assert second.world_created is False
    assert second_ids == first_ids


def test_existing_real_fixture_geography_resolves(mapped_session: Session) -> None:
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))["data"][0]
    reporter = resolve_source_area(
        mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, record["reporterCode"]
    )
    partner = resolve_source_area(
        mapped_session, SOURCE_AGENCY, SOURCE_SYSTEM, record["partnerCode"]
    )

    assert reporter is not None and reporter.iso3 == "TUN"
    assert partner is not None and partner.area_type is AreaType.AGGREGATE
