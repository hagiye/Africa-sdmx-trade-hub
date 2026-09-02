"""Canonical African Union geography reference and loader tests."""

from __future__ import annotations

import json
from datetime import date
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import AreaType, GeoArea
from app.reference.geo import (
    DEFAULT_REFERENCE_PATH,
    load_geo_reference,
    load_geo_reference_file,
)


def test_reference_file_loads_and_matches_declared_member_count() -> None:
    dataset = load_geo_reference_file()

    assert dataset.areas
    assert len(dataset.areas) == dataset.member_count == 55
    assert all(row.au_member is True for row in dataset.areas)
    assert all(row.area_type == "COUNTRY" for row in dataset.areas)
    assert all(row.iso2 and row.iso3 for row in dataset.areas)


def test_reference_identifiers_are_unique() -> None:
    rows = load_geo_reference_file().areas

    for field in ("iso2", "iso3", "numeric_code"):
        values = [getattr(row, field) for row in rows if getattr(row, field)]
        assert len(values) == len(set(values))


def test_tunisia_canonical_reference() -> None:
    tunisia = next(
        row for row in load_geo_reference_file().areas if row.name_en == "Tunisia"
    )

    assert (tunisia.iso2, tunisia.iso3, tunisia.numeric_code) == (
        "TN",
        "TUN",
        "788",
    )
    assert tunisia.name_fr == "Tunisie"
    assert tunisia.au_member is True


def test_kenya_canonical_reference() -> None:
    kenya = next(
        row for row in load_geo_reference_file().areas if row.name_en == "Kenya"
    )

    assert (kenya.iso2, kenya.iso3, kenya.numeric_code) == (
        "KE",
        "KEN",
        "404",
    )
    assert kenya.name_fr == "Kenya"
    assert kenya.au_member is True


def test_loader_is_idempotent_and_creates_country_rows(db_session: Session) -> None:
    first = load_geo_reference(db_session)
    first_ids = set(db_session.scalars(select(GeoArea.id)))
    second = load_geo_reference(db_session)
    second_ids = set(db_session.scalars(select(GeoArea.id)))

    assert (first.inserted, first.updated, first.unchanged, first.total_rows) == (
        55,
        0,
        0,
        55,
    )
    assert (second.inserted, second.updated, second.unchanged, second.total_rows) == (
        0,
        0,
        55,
        55,
    )
    assert second_ids == first_ids
    assert db_session.scalar(select(func.count()).select_from(GeoArea)) == 55
    assert all(
        area_type is AreaType.COUNTRY
        for area_type in db_session.scalars(select(GeoArea.area_type))
    )


def test_loader_updates_only_managed_fields_and_keeps_unrelated_rows(
    db_session: Session,
) -> None:
    load_geo_reference(db_session)
    tunisia = db_session.scalar(select(GeoArea).where(GeoArea.iso2 == "TN"))
    assert tunisia is not None
    tunisia.name_fr = "Label requiring refresh"
    tunisia.valid_from = date(1963, 5, 25)
    unrelated = GeoArea(
        name_en="Test aggregate",
        name_fr="Agrégat de test",
        area_type=AreaType.AGGREGATE,
        au_member=False,
    )
    db_session.add(unrelated)
    db_session.commit()

    result = load_geo_reference(db_session)

    db_session.refresh(tunisia)
    assert (result.inserted, result.updated, result.unchanged, result.total_rows) == (
        0,
        1,
        54,
        56,
    )
    assert tunisia.name_fr == "Tunisie"
    assert tunisia.valid_from == date(1963, 5, 25)
    assert db_session.get(GeoArea, unrelated.id) is not None


def test_reference_contains_no_provider_mapping_or_world_country() -> None:
    raw = json.loads(DEFAULT_REFERENCE_PATH.read_text(encoding="utf-8"))
    serialized = json.dumps(raw).casefold()

    assert "provider_code" not in serialized
    assert all(row["name_en"] != "World" for row in raw["areas"])
