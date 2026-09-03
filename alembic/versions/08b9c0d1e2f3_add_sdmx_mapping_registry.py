"""add versioned SDMX source-to-target mapping registry

Revision ID: 08b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-09-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "08b9c0d1e2f3"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "sdmx_transformation_definition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transformation_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("implementation_key", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transformation_id",
            "version",
            name="uq_sdmx_transformation_definition_identity",
        ),
    )

    op.create_table(
        "sdmx_concept_mapping",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mapping_definition_id", sa.String(length=255), nullable=False),
        sa.Column("mapping_version", sa.String(length=64), nullable=False),
        sa.Column("definition_checksum", sa.String(length=64), nullable=False),
        sa.Column("source_agency", sa.String(length=128), nullable=False),
        sa.Column("source_structure_id", sa.String(length=255), nullable=False),
        sa.Column("source_structure_version", sa.String(length=64), nullable=False),
        sa.Column("source_concept_id", sa.String(length=255), nullable=False),
        sa.Column("target_agency", sa.String(length=128), nullable=False),
        sa.Column("target_structure_id", sa.String(length=255), nullable=False),
        sa.Column("target_structure_version", sa.String(length=64), nullable=False),
        sa.Column("target_concept_id", sa.String(length=255), nullable=True),
        sa.Column(
            "target_concept_key",
            sa.String(length=255),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column("mapping_type", sa.String(length=9), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("transformation_id", sa.String(length=128), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "mapping_type IN ('DIRECT', 'RENAME', 'TRANSFORM', 'DERIVE', "
            "'DROP', 'DEFER')",
            name="ck_sdmx_concept_mapping_type",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'CONFIRMED', 'MANUAL', 'DEPRECATED')",
            name="ck_sdmx_concept_mapping_status",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_sdmx_concept_mapping_valid_period",
        ),
        sa.CheckConstraint(
            "target_concept_key = COALESCE(target_concept_id, '')",
            name="ck_sdmx_concept_mapping_target_key",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "mapping_definition_id",
            "mapping_version",
            "source_agency",
            "source_structure_id",
            "source_structure_version",
            "source_concept_id",
            "target_agency",
            "target_structure_id",
            "target_structure_version",
            "target_concept_key",
            name="uq_sdmx_concept_mapping_identity",
        ),
    )
    op.create_index(
        "ix_sdmx_concept_mapping_source_target",
        "sdmx_concept_mapping",
        [
            "source_agency",
            "source_structure_id",
            "source_structure_version",
            "target_agency",
            "target_structure_id",
            "target_structure_version",
        ],
    )
    op.create_index(
        "ix_sdmx_concept_mapping_status", "sdmx_concept_mapping", ["status"]
    )

    op.create_table(
        "sdmx_code_mapping",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("concept_mapping_id", sa.Integer(), nullable=False),
        sa.Column("source_codelist_agency", sa.String(length=128), nullable=False),
        sa.Column("source_codelist_id", sa.String(length=255), nullable=False),
        sa.Column("source_codelist_version", sa.String(length=64), nullable=False),
        sa.Column("source_code", sa.String(length=255), nullable=False),
        sa.Column("target_codelist_agency", sa.String(length=128), nullable=True),
        sa.Column("target_codelist_id", sa.String(length=255), nullable=True),
        sa.Column("target_codelist_version", sa.String(length=64), nullable=True),
        sa.Column("target_code", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("mapping_method", sa.String(length=128), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column(
            "validity_context",
            sa.String(length=64),
            server_default=sa.text("'OPEN'"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'CONFIRMED', 'MANUAL', 'DEPRECATED')",
            name="ck_sdmx_code_mapping_status",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_sdmx_code_mapping_valid_period",
        ),
        sa.ForeignKeyConstraint(
            ["concept_mapping_id"],
            ["sdmx_concept_mapping.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "concept_mapping_id",
            "source_codelist_agency",
            "source_codelist_id",
            "source_codelist_version",
            "source_code",
            "validity_context",
            name="uq_sdmx_code_mapping_source_identity",
        ),
    )
    op.create_index(
        "ix_sdmx_code_mapping_concept_mapping_id",
        "sdmx_code_mapping",
        ["concept_mapping_id"],
    )
    op.create_index(
        "ix_sdmx_code_mapping_source_code", "sdmx_code_mapping", ["source_code"]
    )
    op.create_index(
        "ix_sdmx_code_mapping_status", "sdmx_code_mapping", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_sdmx_code_mapping_status", table_name="sdmx_code_mapping")
    op.drop_index("ix_sdmx_code_mapping_source_code", table_name="sdmx_code_mapping")
    op.drop_index(
        "ix_sdmx_code_mapping_concept_mapping_id",
        table_name="sdmx_code_mapping",
    )
    op.drop_table("sdmx_code_mapping")
    op.drop_index(
        "ix_sdmx_concept_mapping_status", table_name="sdmx_concept_mapping"
    )
    op.drop_index(
        "ix_sdmx_concept_mapping_source_target",
        table_name="sdmx_concept_mapping",
    )
    op.drop_table("sdmx_concept_mapping")
    op.drop_table("sdmx_transformation_definition")
