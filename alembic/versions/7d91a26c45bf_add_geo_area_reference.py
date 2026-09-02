"""add canonical geo area reference

Revision ID: 7d91a26c45bf
Revises: 12b008136560
Create Date: 2026-09-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7d91a26c45bf"
down_revision: Union[str, None] = "12b008136560"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "geo_area",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("iso2", sa.String(length=2), nullable=True),
        sa.Column("iso3", sa.String(length=3), nullable=True),
        sa.Column("numeric_code", sa.String(length=3), nullable=True),
        sa.Column("name_en", sa.String(length=255), nullable=False),
        sa.Column("name_fr", sa.String(length=255), nullable=False),
        sa.Column(
            "area_type",
            sa.String(length=9),
            nullable=False,
        ),
        sa.Column(
            "au_member", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("subregion", sa.String(length=128), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
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
            name="ck_geo_area_valid_period",
        ),
        sa.CheckConstraint(
            "area_type IN ('COUNTRY', 'REGION', 'AGGREGATE', 'OTHER')",
            name="area_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_geo_area_iso2",
        "geo_area",
        ["iso2"],
        unique=True,
        postgresql_where=sa.text("iso2 IS NOT NULL"),
        sqlite_where=sa.text("iso2 IS NOT NULL"),
    )
    op.create_index(
        "ux_geo_area_iso3",
        "geo_area",
        ["iso3"],
        unique=True,
        postgresql_where=sa.text("iso3 IS NOT NULL"),
        sqlite_where=sa.text("iso3 IS NOT NULL"),
    )
    op.create_index(
        "ux_geo_area_numeric_code",
        "geo_area",
        ["numeric_code"],
        unique=True,
        postgresql_where=sa.text("numeric_code IS NOT NULL"),
        sqlite_where=sa.text("numeric_code IS NOT NULL"),
    )
    op.create_index("ix_geo_area_au_member", "geo_area", ["au_member"], unique=False)
    op.create_index("ix_geo_area_area_type", "geo_area", ["area_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_geo_area_area_type", table_name="geo_area")
    op.drop_index("ix_geo_area_au_member", table_name="geo_area")
    op.drop_index("ux_geo_area_numeric_code", table_name="geo_area")
    op.drop_index("ux_geo_area_iso3", table_name="geo_area")
    op.drop_index("ux_geo_area_iso2", table_name="geo_area")
    op.drop_table("geo_area")
