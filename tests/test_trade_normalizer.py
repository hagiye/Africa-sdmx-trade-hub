"""Trade normalization tests using real records and explicit synthetic variants."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.database.models import (
    Agency,
    AreaType,
    Code,
    Codelist,
    Dataflow,
    GeoArea,
    MappingStatus,
    SourceGeoMapping,
)
from app.mappings.geo import (
    CODELIST_IDENTITY,
    SOURCE_AGENCY,
    SOURCE_CODELIST,
    SOURCE_SYSTEM,
    load_source_geo_mappings,
)
from app.pipelines.trade_models import NormalizationIssueCode
from app.pipelines.trade_normalizer import normalize_trade_observation
from app.reference.geo import load_geo_reference
from app.sdmx.data_models import ParsedObservation
from app.sdmx.data_parser import parse_comtrade_response


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "data"
FIXTURE_PATHS = sorted(
    FIXTURE_DIRECTORY.glob("un_comtrade_tunisia_imports_world_20*.json")
)
EXPECTED_PRIMARY_VALUES = {
    "2022": Decimal("26672667450.171"),
    "2023": Decimal("25930493874.99"),
    "2024": Decimal("26065070572.389"),
}

# This bounded provider reference is synthetic test data shaped like the official
# partnerAreas response. It exercises the production mapping service offline.
SYNTHETIC_PROVIDER_AREAS = [
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
    {
        "PartnerCode": 999999,
        "PartnerDesc": "Synthetic unresolved area",
        "isGroup": False,
    },
]


def _load_real_observation(path: Path) -> ParsedObservation:
    payload = json.loads(path.read_text(encoding="utf-8"))
    observations = parse_comtrade_response(payload).observations
    assert len(observations) == 1
    return observations[0]


def _synthetic_observation(
    base: ParsedObservation,
    *,
    reporter_code: int = 788,
    reporter_desc: str = "Tunisia",
    reporter_iso3: str = "TUN",
    counterpart_code: int = 0,
    counterpart_desc: str = "World",
) -> ParsedObservation:
    """Derive a clearly synthetic ParsedObservation from the real schema."""
    observation = base.model_copy(deep=True)
    observation.source = "synthetic trade-normalizer test observation"
    observation.source_fields.update(
        {
            "reporterCode": reporter_code,
            "reporterDesc": reporter_desc,
            "reporterISO": reporter_iso3,
            "partnerCode": counterpart_code,
            "partnerDesc": counterpart_desc,
        }
    )
    return observation


@pytest.fixture
def normalization_session(db_session: Session) -> Session:
    load_geo_reference(db_session)
    agency, codelist_id, version = CODELIST_IDENTITY
    db_session.add(Agency(agency_id=agency, name="United Nations Statistics Division"))
    area_codelist = Codelist(
        agency_id=agency,
        codelist_id=codelist_id,
        version=version,
        name="CL_AREA",
        source_url="https://fixtures.invalid/CL_AREA",
        retrieved_at=datetime.now(timezone.utc),
        checksum="a" * 64,
    )
    db_session.add(area_codelist)
    db_session.flush()
    db_session.add_all(
        Code(codelist_id=area_codelist.id, code=code)
        for code in ("W0", "KE", "TN")
    )
    db_session.add(
        Dataflow(
            agency_id="UNSD",
            dataflow_id="IMTS_A",
            version="1.0",
            name="International Merchandise Trade Statistics, Annual",
            source_url="https://fixtures.invalid/IMTS_A",
            retrieved_at=datetime.now(timezone.utc),
            checksum="b" * 64,
            dsd_agency_id="UNSD",
            dsd_id="IMTS",
            dsd_version="1.2",
        )
    )
    db_session.commit()
    load_source_geo_mappings(db_session, SYNTHETIC_PROVIDER_AREAS)

    # No confirmed non-AU provider mapping is part of the controlled reference.
    # Add an explicit in-memory mapping so scope behavior can still be tested.
    canada = GeoArea(
        iso2="CA",
        iso3="CAN",
        numeric_code="124",
        name_en="Canada",
        name_fr="Canada",
        area_type=AreaType.COUNTRY,
        au_member=False,
        region="Americas",
        subregion="Northern America",
    )
    db_session.add(canada)
    db_session.flush()
    db_session.add(
        SourceGeoMapping(
            source_agency=SOURCE_AGENCY,
            source_system=SOURCE_SYSTEM,
            source_codelist=SOURCE_CODELIST,
            source_code="124",
            geo_area_id=canada.id,
            mapping_status=MappingStatus.MANUAL,
            source_label_en="Canada",
            mapping_method="SYNTHETIC_TEST_MAPPING",
        )
    )
    db_session.commit()
    return db_session


@pytest.mark.parametrize("path", FIXTURE_PATHS, ids=lambda path: path.stem[-4:])
def test_real_tunisia_world_fixtures_normalize_end_to_end(
    path: Path, normalization_session: Session
) -> None:
    parsed = _load_real_observation(path)

    result = normalize_trade_observation(parsed, normalization_session)

    assert result.issues == []
    assert result.observation is not None
    normalized = result.observation
    assert normalized.source_agency == "UNSD"
    assert normalized.source_system == "UN_COMTRADE"
    assert normalized.source_dataflow == "IMTS_A"
    assert normalized.source_dataflow_version == "1.0"
    assert normalized.source_dsd == "IMTS"
    assert normalized.source_dsd_version == "1.2"

    assert normalized.reference_area_source_code == "788"
    assert normalized.reference_name == "Tunisia"
    assert normalized.reference_iso2 == "TN"
    assert normalized.reference_iso3 == "TUN"
    assert normalized.reference_area_type is AreaType.COUNTRY
    assert normalized.reference_is_au_member is True

    assert normalized.counterpart_area_source_code == "0"
    assert normalized.counterpart_name == "World"
    assert normalized.counterpart_area_type is AreaType.AGGREGATE
    assert normalized.counterpart_is_au_member is False
    assert normalized.counterpart_iso2 is None
    assert normalized.counterpart_iso3 is None

    assert normalized.trade_flow_code == "M"
    assert normalized.trade_flow_label == "Import"
    assert normalized.frequency_code == "A"  # Annual in SDMX CL_FREQ.
    assert normalized.commodity_code == "TOTAL"
    assert normalized.commodity_classification == "S4"
    assert normalized.commodity_sdmx_code == "SITC4_TOTAL"
    assert normalized.commodity_description == "All Commodities"
    assert normalized.time_period == path.stem[-4:]
    assert normalized.primary_value == EXPECTED_PRIMARY_VALUES[normalized.time_period]
    assert normalized.primary_value == parsed.get_primary_value()
    assert normalized.quantity == parsed.observation_values["qty"]
    assert normalized.net_weight == parsed.observation_values["netWgt"]
    assert normalized.gross_weight == parsed.observation_values["grossWgt"]
    assert normalized.cif_value == parsed.observation_values["cifvalue"]
    assert normalized.fob_value is None

    assert normalized.source_dimensions == parsed.dimension_values
    assert normalized.source_attributes == parsed.attributes
    assert normalized.source_fields == parsed.source_fields
    assert normalized.source_fields["reporterCode"] == 788
    assert normalized.source_fields["partnerCode"] == 0


def test_synthetic_kenya_reporter_resolves_as_au_member(
    normalization_session: Session,
) -> None:
    base = _load_real_observation(FIXTURE_PATHS[0])
    synthetic = _synthetic_observation(
        base,
        reporter_code=404,
        reporter_desc="Kenya",
        reporter_iso3="KEN",
    )

    result = normalize_trade_observation(synthetic, normalization_session)

    assert result.issues == []
    assert result.observation is not None
    assert result.observation.reference_area_source_code == "404"
    assert result.observation.reference_name == "Kenya"
    assert result.observation.reference_iso2 == "KE"
    assert result.observation.reference_iso3 == "KEN"
    assert result.observation.reference_is_au_member is True


def test_synthetic_non_au_reporter_is_normalized_without_filtering(
    normalization_session: Session,
) -> None:
    base = _load_real_observation(FIXTURE_PATHS[0])
    synthetic = _synthetic_observation(
        base,
        reporter_code=124,
        reporter_desc="Canada",
        reporter_iso3="CAN",
    )

    result = normalize_trade_observation(synthetic, normalization_session)

    assert result.issues == []
    assert result.observation is not None
    assert result.observation.reference_name == "Canada"
    assert result.observation.reference_iso2 == "CA"
    assert result.observation.reference_iso3 == "CAN"
    assert result.observation.reference_is_au_member is False


def test_unmapped_reporter_produces_fatal_issue_without_fake_geography(
    normalization_session: Session,
) -> None:
    base = _load_real_observation(FIXTURE_PATHS[0])
    synthetic = _synthetic_observation(
        base,
        reporter_code=999999,
        reporter_desc="Synthetic unresolved area",
        reporter_iso3="ZZZ",
    )

    result = normalize_trade_observation(synthetic, normalization_session)

    assert result.observation is None
    assert result.has_fatal_issues is True
    assert [(issue.code, issue.source_code, issue.fatal) for issue in result.issues] == [
        (NormalizationIssueCode.UNMAPPED_REFERENCE_AREA, "999999", True)
    ]


def test_unmapped_counterpart_is_nonfatal_and_preserves_source_code(
    normalization_session: Session,
) -> None:
    base = _load_real_observation(FIXTURE_PATHS[0])
    synthetic = _synthetic_observation(
        base,
        counterpart_code=999999,
        counterpart_desc="Synthetic unresolved counterpart",
    )

    result = normalize_trade_observation(synthetic, normalization_session)

    assert result.has_fatal_issues is False
    assert result.observation is not None
    assert result.observation.reference_name == "Tunisia"
    assert result.observation.counterpart_area_source_code == "999999"
    assert result.observation.counterpart_geo_id is None
    assert result.observation.counterpart_name is None
    assert result.observation.counterpart_area_type is None
    assert result.observation.source_fields["partnerCode"] == 999999
    assert [(issue.code, issue.source_code, issue.fatal) for issue in result.issues] == [
        (NormalizationIssueCode.UNMAPPED_COUNTERPART_AREA, "999999", False)
    ]
