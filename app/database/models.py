"""SQLAlchemy 2 models for the SDMX metadata registry."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AreaType(StrEnum):
    COUNTRY = "COUNTRY"
    REGION = "REGION"
    AGGREGATE = "AGGREGATE"
    OTHER = "OTHER"


class MappingStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    AUTO_MATCHED = "AUTO_MATCHED"
    MANUAL = "MANUAL"
    UNMAPPED = "UNMAPPED"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class GeoArea(TimestampMixin, Base):
    __tablename__ = "geo_area"
    __table_args__ = (
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_geo_area_valid_period",
        ),
        CheckConstraint(
            "area_type IN ('COUNTRY', 'REGION', 'AGGREGATE', 'OTHER')",
            name="area_type",
        ),
        Index(
            "ux_geo_area_iso2",
            "iso2",
            unique=True,
            postgresql_where=text("iso2 IS NOT NULL"),
            sqlite_where=text("iso2 IS NOT NULL"),
        ),
        Index(
            "ux_geo_area_iso3",
            "iso3",
            unique=True,
            postgresql_where=text("iso3 IS NOT NULL"),
            sqlite_where=text("iso3 IS NOT NULL"),
        ),
        Index(
            "ux_geo_area_numeric_code",
            "numeric_code",
            unique=True,
            postgresql_where=text("numeric_code IS NOT NULL"),
            sqlite_where=text("numeric_code IS NOT NULL"),
        ),
        Index("ix_geo_area_au_member", "au_member"),
        Index("ix_geo_area_area_type", "area_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    iso2: Mapped[str | None] = mapped_column(String(2))
    iso3: Mapped[str | None] = mapped_column(String(3))
    numeric_code: Mapped[str | None] = mapped_column(String(3))
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    name_fr: Mapped[str] = mapped_column(String(255), nullable=False)
    area_type: Mapped[AreaType] = mapped_column(
        SAEnum(
            AreaType,
            name="area_type",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    au_member: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    region: Mapped[str | None] = mapped_column(String(128))
    subregion: Mapped[str | None] = mapped_column(String(128))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class SourceGeoMapping(TimestampMixin, Base):
    __tablename__ = "source_geo_mapping"
    __table_args__ = (
        UniqueConstraint(
            "source_agency",
            "source_system",
            "source_codelist",
            "source_code",
            name="uq_source_geo_mapping_identity",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_source_geo_mapping_valid_period",
        ),
        CheckConstraint(
            "mapping_status IN "
            "('CONFIRMED', 'AUTO_MATCHED', 'MANUAL', 'UNMAPPED')",
            name="mapping_status",
        ),
        Index("ix_source_geo_mapping_source_code", "source_code"),
        Index("ix_source_geo_mapping_source_system", "source_system"),
        Index("ix_source_geo_mapping_geo_area_id", "geo_area_id"),
        Index("ix_source_geo_mapping_mapping_status", "mapping_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_agency: Mapped[str] = mapped_column(String(128), nullable=False)
    source_system: Mapped[str] = mapped_column(String(128), nullable=False)
    source_codelist: Mapped[str] = mapped_column(String(255), nullable=False)
    source_code: Mapped[str] = mapped_column(String(128), nullable=False)
    geo_area_id: Mapped[int | None] = mapped_column(
        ForeignKey("geo_area.id", ondelete="SET NULL")
    )
    mapping_status: Mapped[MappingStatus] = mapped_column(
        SAEnum(
            MappingStatus,
            name="mapping_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    source_label_en: Mapped[str | None] = mapped_column(String(512))
    source_label_fr: Mapped[str | None] = mapped_column(String(512))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    mapping_method: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str | None] = mapped_column(Text)
    geo_area: Mapped[GeoArea | None] = relationship()


class Agency(TimestampMixin, Base):
    __tablename__ = "sdmx_agency"

    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)


class Dataflow(TimestampMixin, Base):
    __tablename__ = "sdmx_dataflow"
    __table_args__ = (UniqueConstraint("agency_id", "dataflow_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[str] = mapped_column(
        ForeignKey("sdmx_agency.agency_id"), nullable=False
    )
    dataflow_id: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_external_reference: Mapped[bool] = mapped_column(default=False, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    dsd_agency_id: Mapped[str | None] = mapped_column(String(128))
    dsd_id: Mapped[str | None] = mapped_column(String(255))
    dsd_version: Mapped[str | None] = mapped_column(String(64))


class DSD(TimestampMixin, Base):
    __tablename__ = "sdmx_dsd"
    __table_args__ = (UniqueConstraint("agency_id", "dsd_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[str] = mapped_column(
        ForeignKey("sdmx_agency.agency_id"), nullable=False
    )
    dsd_id: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    dimensions: Mapped[list[Dimension]] = relationship(
        cascade="all, delete-orphan", back_populates="dsd", order_by="Dimension.position"
    )
    attributes: Mapped[list[Attribute]] = relationship(
        cascade="all, delete-orphan", back_populates="dsd"
    )
    measures: Mapped[list[Measure]] = relationship(
        cascade="all, delete-orphan", back_populates="dsd"
    )


class ConceptScheme(TimestampMixin, Base):
    __tablename__ = "sdmx_concept_scheme"
    __table_args__ = (UniqueConstraint("agency_id", "scheme_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[str] = mapped_column(
        ForeignKey("sdmx_agency.agency_id"), nullable=False
    )
    scheme_id: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    concepts: Mapped[list[Concept]] = relationship(
        cascade="all, delete-orphan", back_populates="concept_scheme"
    )


class Concept(TimestampMixin, Base):
    __tablename__ = "sdmx_concept"
    __table_args__ = (UniqueConstraint("concept_scheme_id", "concept_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    concept_scheme_id: Mapped[int] = mapped_column(
        ForeignKey("sdmx_concept_scheme.id", ondelete="CASCADE"), nullable=False
    )
    concept_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    concept_scheme: Mapped[ConceptScheme] = relationship(back_populates="concepts")


class Codelist(TimestampMixin, Base):
    __tablename__ = "sdmx_codelist"
    __table_args__ = (UniqueConstraint("agency_id", "codelist_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[str] = mapped_column(
        ForeignKey("sdmx_agency.agency_id"), nullable=False
    )
    codelist_id: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    codes: Mapped[list[Code]] = relationship(
        cascade="all, delete-orphan", back_populates="codelist"
    )


class Code(TimestampMixin, Base):
    __tablename__ = "sdmx_code"
    __table_args__ = (UniqueConstraint("codelist_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    codelist_id: Mapped[int] = mapped_column(
        ForeignKey("sdmx_codelist.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_code: Mapped[str | None] = mapped_column(String(255))
    codelist: Mapped[Codelist] = relationship(back_populates="codes")


class LocalizedLabel(Base):
    __tablename__ = "sdmx_localized_label"
    __table_args__ = (UniqueConstraint("entity_type", "entity_pk", "language"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_pk: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)


class Dimension(Base):
    __tablename__ = "sdmx_dimension"
    __table_args__ = (UniqueConstraint("dsd_id", "concept_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dsd_id: Mapped[int] = mapped_column(ForeignKey("sdmx_dsd.id", ondelete="CASCADE"))
    concept_id: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    codelist_agency_id: Mapped[str | None] = mapped_column(String(128))
    codelist_id: Mapped[str | None] = mapped_column(String(255))
    codelist_version: Mapped[str | None] = mapped_column(String(64))
    representation: Mapped[str | None] = mapped_column(Text)
    dsd: Mapped[DSD] = relationship(back_populates="dimensions")


class Attribute(Base):
    __tablename__ = "sdmx_attribute"
    __table_args__ = (UniqueConstraint("dsd_id", "concept_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dsd_id: Mapped[int] = mapped_column(ForeignKey("sdmx_dsd.id", ondelete="CASCADE"))
    concept_id: Mapped[str] = mapped_column(String(255), nullable=False)
    attachment_level: Mapped[str | None] = mapped_column(String(255))
    codelist_agency_id: Mapped[str | None] = mapped_column(String(128))
    codelist_id: Mapped[str | None] = mapped_column(String(255))
    codelist_version: Mapped[str | None] = mapped_column(String(64))
    representation: Mapped[str | None] = mapped_column(Text)
    dsd: Mapped[DSD] = relationship(back_populates="attributes")


class Measure(Base):
    __tablename__ = "sdmx_measure"
    __table_args__ = (UniqueConstraint("dsd_id", "concept_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dsd_id: Mapped[int] = mapped_column(ForeignKey("sdmx_dsd.id", ondelete="CASCADE"))
    concept_id: Mapped[str] = mapped_column(String(255), nullable=False)
    representation: Mapped[str | None] = mapped_column(Text)
    dsd: Mapped[DSD] = relationship(back_populates="measures")


class StructureImport(Base):
    __tablename__ = "sdmx_structure_import"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    structures_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    structures_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    structures_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum_changes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
