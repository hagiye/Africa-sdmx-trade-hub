"""add UN Comtrade source geography mapping

Revision ID: 9c341cb786a2
Revises: 7d91a26c45bf
Create Date: 2026-09-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c341cb786a2"
down_revision: Union[str, None] = "7d91a26c45bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_geo_mapping",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_agency", sa.String(length=128), nullable=False),
        sa.Column("source_system", sa.String(length=128), nullable=False),
        sa.Column("source_codelist", sa.String(length=255), nullable=False),
        sa.Column("source_code", sa.String(length=128), nullable=False),
        sa.Column("geo_area_id", sa.Integer(), nullable=True),
        sa.Column("mapping_status", sa.String(length=12), nullable=False),
        sa.Column("source_label_en", sa.String(length=512), nullable=True),
        sa.Column("source_label_fr", sa.String(length=512), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("mapping_method", sa.String(length=128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_source_geo_mapping_valid_period",
        ),
        sa.CheckConstraint(
            "mapping_status IN "
            "('CONFIRMED', 'AUTO_MATCHED', 'MANUAL', 'UNMAPPED')",
            name="mapping_status",
        ),
        sa.ForeignKeyConstraint(
            ["geo_area_id"], ["geo_area.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_agency",
            "source_system",
            "source_codelist",
            "source_code",
            name="uq_source_geo_mapping_identity",
        ),
    )
    op.create_index(
        "ix_source_geo_mapping_source_code",
        "source_geo_mapping",
        ["source_code"],
        unique=False,
    )
    op.create_index(
        "ix_source_geo_mapping_source_system",
        "source_geo_mapping",
        ["source_system"],
        unique=False,
    )
    op.create_index(
        "ix_source_geo_mapping_geo_area_id",
        "source_geo_mapping",
        ["geo_area_id"],
        unique=False,
    )
    op.create_index(
        "ix_source_geo_mapping_mapping_status",
        "source_geo_mapping",
        ["mapping_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_geo_mapping_mapping_status", table_name="source_geo_mapping"
    )
    op.drop_index("ix_source_geo_mapping_geo_area_id", table_name="source_geo_mapping")
    op.drop_index("ix_source_geo_mapping_source_system", table_name="source_geo_mapping")
    op.drop_index("ix_source_geo_mapping_source_code", table_name="source_geo_mapping")
    op.drop_table("source_geo_mapping")
