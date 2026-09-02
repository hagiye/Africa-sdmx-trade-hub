"""Database-backed UN Comtrade to canonical geography mappings."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import requests
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import (
    AreaType,
    Code,
    Codelist,
    GeoArea,
    MappingStatus,
    SourceGeoMapping,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIRMED_REFERENCE_PATH = (
    ROOT / "data" / "reference" / "un_comtrade_geo_confirmed.json"
)
SOURCE_AGENCY = "UNSD"
SOURCE_SYSTEM = "UN_COMTRADE"
SOURCE_CODELIST = "UNSD:CL_AREA(1.0)"
CODELIST_IDENTITY = ("UNSD", "CL_AREA", "1.0")
PARTNER_AREAS_URL = (
    "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json"
)
MAX_REFERENCE_BYTES = 2 * 1024 * 1024


class SourceGeoMappingError(ValueError):
    """Source geography metadata or mapping state is inconsistent."""


class ConfirmedMapping(BaseModel):
    source_code: str = Field(pattern=r"^[0-9]+$")
    source_label_en: str
    structural_code: str
    canonical_name_en: str
    canonical_name_fr: str
    canonical_iso2: str | None
    canonical_iso3: str | None
    area_type: Literal["COUNTRY", "AGGREGATE"]
    mapping_status: Literal["CONFIRMED"]
    mapping_method: str


class ConfirmedMappingDataset(BaseModel):
    source_agency: Literal["UNSD"]
    source_system: Literal["UN_COMTRADE"]
    source_codelist: Literal["UNSD:CL_AREA(1.0)"]
    provider_reference: str
    verified_on: str
    mappings: list[ConfirmedMapping]


@dataclass(frozen=True)
class ProviderArea:
    code: str
    label_en: str
    iso2: str | None
    iso3: str | None
    valid_from: date | None
    valid_to: date | None
    is_group: bool
    note: str | None


@dataclass(frozen=True)
class SourceGeoLoadResult:
    source_codes_examined: int
    inserted: int
    updated: int
    unchanged: int
    mapped: int
    unmapped: int
    total_mappings: int
    world_created: bool


MAPPING_MANAGED_FIELDS = (
    "geo_area_id",
    "mapping_status",
    "source_label_en",
    "source_label_fr",
    "valid_from",
    "valid_to",
    "mapping_method",
    "notes",
)


def load_confirmed_mappings(
    path: Path = CONFIRMED_REFERENCE_PATH,
) -> ConfirmedMappingDataset:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        dataset = ConfirmedMappingDataset.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise SourceGeoMappingError(
            f"Invalid confirmed geography mapping reference {path}: {exc}"
        ) from exc
    codes = [mapping.source_code for mapping in dataset.mappings]
    if len(codes) != len(set(codes)):
        raise SourceGeoMappingError("Confirmed geography mapping codes are not unique")
    return dataset


def fetch_un_comtrade_partner_areas(
    *, timeout_seconds: float = 60.0
) -> list[dict[str, Any]]:
    """Fetch the official bounded UN Comtrade partner geography reference."""
    try:
        with requests.get(
            PARTNER_AREAS_URL,
            timeout=(10.0, timeout_seconds),
            headers={
                "Accept": "application/json",
                "User-Agent": "africa-sdmx-trade-hub/0.1 (+reference loader)",
            },
            stream=True,
        ) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_content(8192):
                body.extend(chunk)
                if len(body) > MAX_REFERENCE_BYTES:
                    raise SourceGeoMappingError(
                        "UN Comtrade partner reference exceeded the 2 MiB limit"
                    )
    except requests.RequestException as exc:
        raise SourceGeoMappingError(
            f"Unable to fetch UN Comtrade partner reference: {exc}"
        ) from exc
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceGeoMappingError(
            "UN Comtrade partner reference is not valid JSON"
        ) from exc
    records = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise SourceGeoMappingError(
            "UN Comtrade partner reference has no results object array"
        )
    return records


def _parse_date(value: object, field: str, code: str) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise SourceGeoMappingError(
            f"Provider code {code} has non-string {field}: {value!r}"
        )
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise SourceGeoMappingError(
            f"Provider code {code} has invalid {field}: {value!r}"
        ) from exc


def _normalize_provider_records(
    records: Sequence[Mapping[str, object]],
) -> list[ProviderArea]:
    normalized = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        raw_code = record.get("PartnerCode")
        if isinstance(raw_code, bool) or not isinstance(raw_code, (int, str)):
            raise SourceGeoMappingError(
                f"Provider area at index {index} has invalid PartnerCode: {raw_code!r}"
            )
        code = str(raw_code).strip()
        if not code.isdigit():
            raise SourceGeoMappingError(f"Invalid numeric provider code: {code!r}")
        code = str(int(code))
        if code in seen:
            raise SourceGeoMappingError(f"Duplicate provider geography code: {code}")
        seen.add(code)
        label = record.get("PartnerDesc") or record.get("text")
        if not isinstance(label, str) or not label.strip():
            raise SourceGeoMappingError(f"Provider code {code} has no English label")
        iso2 = record.get("PartnerCodeIsoAlpha2")
        iso3 = record.get("PartnerCodeIsoAlpha3")
        normalized.append(
            ProviderArea(
                code=code,
                label_en=label.strip(),
                iso2=iso2.strip().upper() if isinstance(iso2, str) and iso2.strip() else None,
                iso3=iso3.strip().upper() if isinstance(iso3, str) and iso3.strip() else None,
                valid_from=_parse_date(record.get("entryEffectiveDate"), "entryEffectiveDate", code),
                valid_to=_parse_date(record.get("entryExpiredDate"), "entryExpiredDate", code),
                is_group=record.get("isGroup") is True,
                note=(
                    str(record["partnerNote"]).strip()
                    if record.get("partnerNote") not in (None, "")
                    else None
                ),
            )
        )
    return normalized


def _source_codelist(session: Session) -> Codelist:
    agency, codelist_id, version = CODELIST_IDENTITY
    codelist = session.scalar(
        select(Codelist).where(
            Codelist.agency_id == agency,
            Codelist.codelist_id == codelist_id,
            Codelist.version == version,
        )
    )
    if codelist is None:
        raise SourceGeoMappingError(
            f"Required structural codelist {SOURCE_CODELIST} is not imported"
        )
    return codelist


def _verify_confirmed_structural_codes(
    session: Session,
    codelist: Codelist,
    confirmed: ConfirmedMappingDataset,
) -> None:
    required = {mapping.structural_code for mapping in confirmed.mappings}
    present = set(
        session.scalars(
            select(Code.code).where(
                Code.codelist_id == codelist.id,
                Code.code.in_(required),
            )
        )
    )
    missing = required - present
    if missing:
        raise SourceGeoMappingError(
            f"Confirmed structural area codes are absent from {SOURCE_CODELIST}: "
            f"{sorted(missing)}"
        )


def _ensure_world(session: Session, override: ConfirmedMapping) -> tuple[GeoArea, bool]:
    matches = list(
        session.scalars(select(GeoArea).where(GeoArea.name_en == override.canonical_name_en))
    )
    if len(matches) > 1:
        raise SourceGeoMappingError("Canonical World exists more than once")
    if matches:
        world = matches[0]
        if (
            world.area_type is not AreaType.AGGREGATE
            or world.au_member
            or world.iso2 is not None
            or world.iso3 is not None
            or world.numeric_code is not None
        ):
            raise SourceGeoMappingError(
                "Canonical World must be an aggregate without ISO country identifiers"
            )
        if world.name_fr != override.canonical_name_fr:
            world.name_fr = override.canonical_name_fr
        return world, False
    world = GeoArea(
        iso2=None,
        iso3=None,
        numeric_code=None,
        name_en=override.canonical_name_en,
        name_fr=override.canonical_name_fr,
        area_type=AreaType.AGGREGATE,
        au_member=False,
        region=None,
        subregion=None,
    )
    session.add(world)
    session.flush()
    return world, True


def _compatible(provider: ProviderArea, area: GeoArea) -> bool:
    return not (
        (provider.iso2 and area.iso2 and provider.iso2 != area.iso2)
        or (provider.iso3 and area.iso3 and provider.iso3 != area.iso3)
    )


def _automatic_match(
    provider: ProviderArea,
    *,
    by_numeric: dict[str, GeoArea],
    by_iso2: dict[str, GeoArea],
    by_iso3: dict[str, GeoArea],
) -> tuple[GeoArea | None, str | None]:
    # Expired entities and provider groups are deliberately not auto-mapped.
    if provider.valid_to is not None or provider.is_group:
        return None, None
    numeric = provider.code.zfill(3) if len(provider.code) <= 3 else None
    if numeric and (candidate := by_numeric.get(numeric)) and _compatible(provider, candidate):
        return candidate, "ISO_NUMERIC_EXACT"
    if provider.iso2 and (candidate := by_iso2.get(provider.iso2)) and _compatible(provider, candidate):
        return candidate, "ISO2_EXACT"
    if provider.iso3 and (candidate := by_iso3.get(provider.iso3)) and _compatible(provider, candidate):
        return candidate, "ISO3_EXACT"
    return None, None


def _validate_confirmed_target(
    provider: ProviderArea,
    area: GeoArea,
    confirmed: ConfirmedMapping,
) -> None:
    expected_type = AreaType(confirmed.area_type)
    actual = (area.name_en, area.iso2, area.iso3, area.area_type)
    expected = (
        confirmed.canonical_name_en,
        confirmed.canonical_iso2,
        confirmed.canonical_iso3,
        expected_type,
    )
    if actual != expected:
        raise SourceGeoMappingError(
            f"Confirmed provider code {provider.code} target mismatch: "
            f"expected {expected}, found {actual}"
        )
    if provider.label_en != confirmed.source_label_en:
        raise SourceGeoMappingError(
            f"Confirmed provider code {provider.code} label changed from "
            f"{confirmed.source_label_en!r} to {provider.label_en!r}"
        )


def load_source_geo_mappings(
    session: Session,
    provider_records: Sequence[Mapping[str, object]],
    *,
    confirmed_path: Path = CONFIRMED_REFERENCE_PATH,
) -> SourceGeoLoadResult:
    """Idempotently map every supplied provider code or retain it as UNMAPPED."""
    confirmed_dataset = load_confirmed_mappings(confirmed_path)
    codelist = _source_codelist(session)
    _verify_confirmed_structural_codes(session, codelist, confirmed_dataset)
    confirmed_by_code = {
        mapping.source_code: mapping for mapping in confirmed_dataset.mappings
    }
    world_override = confirmed_by_code.get("0")
    if world_override is None:
        raise SourceGeoMappingError("Controlled World mapping is missing")
    world, world_created = _ensure_world(session, world_override)

    canonical = list(session.scalars(select(GeoArea)))
    by_numeric = {area.numeric_code: area for area in canonical if area.numeric_code}
    by_iso2 = {area.iso2: area for area in canonical if area.iso2}
    by_iso3 = {area.iso3: area for area in canonical if area.iso3}
    normalized = _normalize_provider_records(provider_records)

    existing_by_code = {
        mapping.source_code: mapping
        for mapping in session.scalars(
            select(SourceGeoMapping).where(
                SourceGeoMapping.source_agency == SOURCE_AGENCY,
                SourceGeoMapping.source_system == SOURCE_SYSTEM,
                SourceGeoMapping.source_codelist == SOURCE_CODELIST,
            )
        )
    }
    inserted = updated = unchanged = mapped_count = unmapped_count = 0

    for provider in normalized:
        existing = existing_by_code.get(provider.code)
        area, method = _automatic_match(
            provider,
            by_numeric=by_numeric,
            by_iso2=by_iso2,
            by_iso3=by_iso3,
        )
        if (
            area is None
            and existing is not None
            and existing.geo_area_id is not None
            and existing.mapping_status is MappingStatus.CONFIRMED
        ):
            area = existing.geo_area
            method = existing.mapping_method
            status = MappingStatus.CONFIRMED
        elif area is not None:
            status = MappingStatus.AUTO_MATCHED
        else:
            status = MappingStatus.UNMAPPED
            method = None

        confirmed = confirmed_by_code.get(provider.code)
        if confirmed is not None:
            if provider.code == "0":
                area = world
            elif confirmed.canonical_iso2:
                area = by_iso2.get(confirmed.canonical_iso2)
            if area is None:
                raise SourceGeoMappingError(
                    f"Confirmed target missing for provider code {provider.code}"
                )
            _validate_confirmed_target(provider, area, confirmed)
            status = MappingStatus.CONFIRMED
            method = confirmed.mapping_method

        # A manual override is the final, explicitly reviewed decision.
        if (
            existing is not None
            and existing.geo_area_id is not None
            and existing.mapping_status is MappingStatus.MANUAL
        ):
            area = existing.geo_area
            status = MappingStatus.MANUAL
            method = existing.mapping_method

        values = {
            "geo_area_id": area.id if area else None,
            "mapping_status": status,
            "source_label_en": provider.label_en,
            "source_label_fr": None,
            "valid_from": provider.valid_from,
            "valid_to": provider.valid_to,
            "mapping_method": method,
            "notes": provider.note,
        }
        if status is MappingStatus.UNMAPPED:
            unmapped_count += 1
        else:
            mapped_count += 1

        if existing is None:
            mapping = SourceGeoMapping(
                source_agency=SOURCE_AGENCY,
                source_system=SOURCE_SYSTEM,
                source_codelist=SOURCE_CODELIST,
                source_code=provider.code,
                **values,
            )
            session.add(mapping)
            existing_by_code[provider.code] = mapping
            inserted += 1
            continue
        changed = False
        for field in MAPPING_MANAGED_FIELDS:
            if getattr(existing, field) != values[field]:
                setattr(existing, field, values[field])
                changed = True
        if changed:
            updated += 1
        else:
            unchanged += 1

    session.commit()
    total = session.scalar(
        select(func.count()).select_from(SourceGeoMapping).where(
            SourceGeoMapping.source_agency == SOURCE_AGENCY,
            SourceGeoMapping.source_system == SOURCE_SYSTEM,
            SourceGeoMapping.source_codelist == SOURCE_CODELIST,
        )
    ) or 0
    return SourceGeoLoadResult(
        source_codes_examined=len(normalized),
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        mapped=mapped_count,
        unmapped=unmapped_count,
        total_mappings=total,
        world_created=world_created,
    )


def resolve_source_mapping(
    session: Session,
    source_agency: str,
    source_system: str,
    source_code: str | int,
    *,
    source_codelist: str = SOURCE_CODELIST,
) -> SourceGeoMapping | None:
    return session.scalar(
        select(SourceGeoMapping).where(
            SourceGeoMapping.source_agency == source_agency,
            SourceGeoMapping.source_system == source_system,
            SourceGeoMapping.source_codelist == source_codelist,
            SourceGeoMapping.source_code == str(source_code),
        )
    )


def resolve_source_area(
    session: Session,
    source_agency: str,
    source_system: str,
    source_code: str | int,
    *,
    source_codelist: str = SOURCE_CODELIST,
) -> GeoArea | None:
    mapping = resolve_source_mapping(
        session,
        source_agency,
        source_system,
        source_code,
        source_codelist=source_codelist,
    )
    return mapping.geo_area if mapping and mapping.geo_area_id is not None else None


def is_au_member(
    session: Session,
    source_agency: str,
    source_system: str,
    source_code: str | int,
) -> bool:
    area = resolve_source_area(session, source_agency, source_system, source_code)
    return bool(area and area.au_member)


def is_au_reporter(
    session: Session,
    source_agency: str,
    source_system: str,
    source_code: str | int,
) -> bool:
    area = resolve_source_area(session, source_agency, source_system, source_code)
    return bool(
        area and area.area_type is AreaType.COUNTRY and area.au_member
    )
