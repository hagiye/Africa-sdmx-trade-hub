"""Validated, idempotent loading of canonical geography reference data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database.models import AreaType, GeoArea


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE_PATH = ROOT / "data" / "reference" / "au_member_states.json"


class GeoReferenceError(ValueError):
    """The canonical geography reference is invalid or internally conflicting."""


class GeoReferenceRow(BaseModel):
    iso2: str = Field(pattern=r"^[A-Z]{2}$")
    iso3: str = Field(pattern=r"^[A-Z]{3}$")
    numeric_code: str = Field(pattern=r"^[0-9]{3}$")
    name_en: str = Field(min_length=1)
    name_fr: str = Field(min_length=1)
    area_type: Literal["COUNTRY"]
    au_member: Literal[True]
    region: str = Field(min_length=1)
    subregion: str = Field(min_length=1)


class GeoReferenceDataset(BaseModel):
    membership_source: str
    identifier_source: str
    verified_on: str
    member_count: int = Field(gt=0)
    areas: list[GeoReferenceRow]

    @model_validator(mode="after")
    def validate_count_and_identifiers(self) -> "GeoReferenceDataset":
        if len(self.areas) != self.member_count:
            raise ValueError(
                f"member_count={self.member_count} but file has {len(self.areas)} rows"
            )
        for field in ("iso2", "iso3", "numeric_code"):
            values = [getattr(row, field) for row in self.areas]
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate {field} in geography reference")
        return self


@dataclass(frozen=True)
class GeoLoadResult:
    inserted: int
    updated: int
    unchanged: int
    total_rows: int


MANAGED_FIELDS = (
    "iso2",
    "iso3",
    "numeric_code",
    "name_en",
    "name_fr",
    "area_type",
    "au_member",
    "region",
    "subregion",
)


def load_geo_reference_file(
    path: Path = DEFAULT_REFERENCE_PATH,
) -> GeoReferenceDataset:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return GeoReferenceDataset.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise GeoReferenceError(f"Invalid geography reference {path}: {exc}") from exc


def _find_existing(session: Session, row: GeoReferenceRow) -> GeoArea | None:
    matches = list(
        session.scalars(
            select(GeoArea).where(
                or_(
                    GeoArea.iso2 == row.iso2,
                    GeoArea.iso3 == row.iso3,
                    GeoArea.numeric_code == row.numeric_code,
                )
            )
        )
    )
    if len(matches) > 1:
        raise GeoReferenceError(
            f"Canonical identifiers for {row.name_en} match multiple geo_area rows"
        )
    return matches[0] if matches else None


def load_geo_reference(
    session: Session,
    path: Path = DEFAULT_REFERENCE_PATH,
) -> GeoLoadResult:
    dataset = load_geo_reference_file(path)
    inserted = updated = unchanged = 0

    for reference in dataset.areas:
        existing = _find_existing(session, reference)
        values = reference.model_dump()
        values["area_type"] = AreaType(reference.area_type)
        if existing is None:
            session.add(GeoArea(**values))
            session.flush()
            inserted += 1
            continue

        changed = False
        for field in MANAGED_FIELDS:
            new_value = values[field]
            if getattr(existing, field) != new_value:
                setattr(existing, field, new_value)
                changed = True
        if changed:
            updated += 1
        else:
            unchanged += 1

    session.commit()
    total_rows = session.scalar(select(func.count()).select_from(GeoArea)) or 0
    return GeoLoadResult(inserted, updated, unchanged, total_rows)
