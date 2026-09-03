"""add persistent validation results

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-09-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "validation_result",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ingestion_batch_id", sa.Integer(), nullable=False),
        sa.Column("observation_id", sa.Integer(), nullable=True),
        sa.Column("observation_rejection_id", sa.Integer(), nullable=True),
        sa.Column("source_key_hash", sa.String(length=64), nullable=True),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=7), nullable=False),
        sa.Column("concept_id", sa.String(length=255), nullable=True),
        sa.Column("invalid_value", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('STRUCTURE', 'CODELIST', 'VALUE', 'GEOGRAPHY', "
            "'APPLICATION_SCOPE', 'QUALITY')",
            name="ck_validation_result_category",
        ),
        sa.CheckConstraint(
            "severity IN ('INFO', 'WARNING', 'ERROR', 'FATAL')",
            name="ck_validation_result_severity",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_batch_id"], ["ingestion_batch.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"], ["trade_observation.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["observation_rejection_id"],
            ["observation_rejection.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_validation_result_ingestion_batch_id",
        "validation_result",
        ["ingestion_batch_id"],
    )
    op.create_index(
        "ix_validation_result_observation_id",
        "validation_result",
        ["observation_id"],
    )
    op.create_index(
        "ix_validation_result_observation_rejection_id",
        "validation_result",
        ["observation_rejection_id"],
    )
    op.create_index(
        "ix_validation_result_rule_severity",
        "validation_result",
        ["rule_id", "severity"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_validation_result_rule_severity", table_name="validation_result"
    )
    op.drop_index(
        "ix_validation_result_observation_rejection_id",
        table_name="validation_result",
    )
    op.drop_index(
        "ix_validation_result_observation_id", table_name="validation_result"
    )
    op.drop_index(
        "ix_validation_result_ingestion_batch_id",
        table_name="validation_result",
    )
    op.drop_table("validation_result")
