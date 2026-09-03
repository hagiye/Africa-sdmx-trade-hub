"""Batch-scoped metadata lookups used by validation rules."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import models as db
from app.mappings.geo import SOURCE_CODELIST
from app.pipelines.observation_identity import build_dataset_identity


# These are the IMTS dimensions the current simplified Comtrade JSON mapping
# actually exposes directly or through a confirmed translation. The full DSD
# contains additional dimensions that this API representation does not expose.
CURRENT_COMTRADE_REQUIRED_DIMENSIONS = (
    "FREQ",
    "REF_AREA",
    "TRADE_FLOW",
    "COMMODITY_1",
    "COUNTERPART_AREA_1",
    "COUNTERPART_AREA_2",
    "TIME_PERIOD",
)


@dataclass(frozen=True)
class DimensionMetadata:
    concept_id: str
    position: int
    role: str
    codelist_identity: tuple[str, str, str] | None


@dataclass(frozen=True)
class GeographyMetadata:
    source_code: str
    mapping_status: db.MappingStatus
    geo_area_id: int | None
    area_type: db.AreaType | None
    au_member: bool | None
    name: str | None


@dataclass
class ValidationContext:
    """Metadata snapshot loaded once and reused for every rule in a batch."""

    dataset_id: int
    dataset_identity: str
    source_agency: str
    source_system: str
    dsd_identity: tuple[str, str, str]
    dimensions: dict[str, DimensionMetadata]
    codelist_codes: dict[str, frozenset[str]]
    concepts: dict[str, str]
    geographies: dict[str, GeographyMetadata]
    required_dimensions: tuple[str, ...] = CURRENT_COMTRADE_REQUIRED_DIMENSIONS
    seen_source_key_hashes: set[str] = field(default_factory=set)
    session: Session | None = field(default=None, repr=False)

    def codes_for(self, concept_id: str) -> frozenset[str] | None:
        return self.codelist_codes.get(concept_id)

    @classmethod
    def from_session(
        cls,
        session: Session,
        dataset: db.StatDataset,
    ) -> "ValidationContext":
        dsd = session.scalar(
            select(db.DSD).where(
                db.DSD.agency_id == dataset.dsd_agency,
                db.DSD.dsd_id == dataset.dsd_id,
                db.DSD.version == dataset.dsd_version,
            )
        )
        dimension_rows = [] if dsd is None else list(
            session.scalars(
                select(db.Dimension)
                .where(db.Dimension.dsd_id == dsd.id)
                .order_by(db.Dimension.position)
            )
        )
        dimensions = {
            row.concept_id: DimensionMetadata(
                concept_id=row.concept_id,
                position=row.position,
                role=row.role,
                codelist_identity=(
                    row.codelist_agency_id,
                    row.codelist_id,
                    row.codelist_version,
                )
                if all(
                    (
                        row.codelist_agency_id,
                        row.codelist_id,
                        row.codelist_version,
                    )
                )
                else None,
            )
            for row in dimension_rows
        }

        identities = {
            metadata.codelist_identity
            for metadata in dimensions.values()
            if metadata.codelist_identity is not None
        }
        codelists: list[db.Codelist] = []
        if identities:
            codelists = list(
                session.scalars(
                    select(db.Codelist).where(
                        or_(
                            *(
                                (
                                    (db.Codelist.agency_id == agency)
                                    & (db.Codelist.codelist_id == codelist_id)
                                    & (db.Codelist.version == version)
                                )
                                for agency, codelist_id, version in identities
                            )
                        )
                    )
                )
            )
        codelist_ids = [row.id for row in codelists]
        codes_by_id: dict[int, set[str]] = {row.id: set() for row in codelists}
        if codelist_ids:
            for codelist_id, code in session.execute(
                select(db.Code.codelist_id, db.Code.code).where(
                    db.Code.codelist_id.in_(codelist_ids)
                )
            ):
                codes_by_id[codelist_id].add(code)
        id_by_identity = {
            (row.agency_id, row.codelist_id, row.version): row.id
            for row in codelists
        }
        codelist_codes = {
            concept_id: frozenset(codes_by_id[id_by_identity[metadata.codelist_identity]])
            for concept_id, metadata in dimensions.items()
            if metadata.codelist_identity in id_by_identity
        }

        concept_ids = set(dimensions)
        concepts = {
            concept_id: name
            for concept_id, name in session.execute(
                select(db.Concept.concept_id, db.Concept.name).where(
                    db.Concept.concept_id.in_(concept_ids)
                )
            )
        } if concept_ids else {}

        geography_rows = session.execute(
            select(db.SourceGeoMapping, db.GeoArea)
            .outerjoin(db.GeoArea, db.SourceGeoMapping.geo_area_id == db.GeoArea.id)
            .where(
                db.SourceGeoMapping.source_agency == dataset.agency,
                db.SourceGeoMapping.source_system == dataset.source_system,
                db.SourceGeoMapping.source_codelist == SOURCE_CODELIST,
            )
        )
        geographies = {
            mapping.source_code: GeographyMetadata(
                source_code=mapping.source_code,
                mapping_status=mapping.mapping_status,
                geo_area_id=area.id if area else None,
                area_type=area.area_type if area else None,
                au_member=area.au_member if area else None,
                name=area.name_en if area else None,
            )
            for mapping, area in geography_rows
        }

        return cls(
            dataset_id=dataset.id,
            dataset_identity=build_dataset_identity(
                dataset.agency, dataset.dataflow_id, dataset.dataflow_version
            ),
            source_agency=dataset.agency,
            source_system=dataset.source_system,
            dsd_identity=(dataset.dsd_agency, dataset.dsd_id, dataset.dsd_version),
            dimensions=dimensions,
            codelist_codes=codelist_codes,
            concepts=concepts,
            geographies=geographies,
            session=session,
        )
