"""add AFR_TRADE harmonization batches, observations, and rejections

Revision ID: 19c0d1e2f3a4
Revises: 08b9c0d1e2f3
Create Date: 2026-09-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "19c0d1e2f3a4"
down_revision: Union[str, None] = "08b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def _count(name: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), server_default=sa.text("0"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "harmonization_batch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_dataset_id", sa.Integer(), nullable=False),
        sa.Column("target_dataset_id", sa.Integer(), nullable=False),
        sa.Column("target_dataflow_agency", sa.String(length=128), nullable=False),
        sa.Column("target_dataflow_id", sa.String(length=255), nullable=False),
        sa.Column("target_dataflow_version", sa.String(length=64), nullable=False),
        sa.Column("target_dsd_agency", sa.String(length=128), nullable=False),
        sa.Column("target_dsd_id", sa.String(length=255), nullable=False),
        sa.Column("target_dsd_version", sa.String(length=64), nullable=False),
        sa.Column("mapping_definition_id", sa.String(length=255), nullable=False),
        sa.Column("mapping_version", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=7), server_default=sa.text("'RUNNING'"), nullable=False),
        _count("source_observations_received"),
        _count("source_observations_valid"),
        _count("observations_transformed"),
        _count("observations_inserted"),
        _count("observations_updated"),
        _count("observations_skipped"),
        _count("observations_rejected"),
        _count("mapping_errors"),
        _count("target_validation_errors"),
        sa.Column("source_batch_id", sa.Integer(), nullable=True),
        sa.Column("mapping_checksum", sa.String(length=64), nullable=True),
        sa.Column("target_structure_checksum", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'SUCCESS', 'PARTIAL', 'FAILED')",
            name="ck_harmonization_batch_status",
        ),
        sa.ForeignKeyConstraint(["source_dataset_id"], ["stat_dataset.id"]),
        sa.ForeignKeyConstraint(["target_dataset_id"], ["stat_dataset.id"]),
        sa.ForeignKeyConstraint(["source_batch_id"], ["ingestion_batch.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_harmonization_batch_source_dataset_id", "harmonization_batch", ["source_dataset_id"])
    op.create_index("ix_harmonization_batch_status", "harmonization_batch", ["status"])

    op.create_table(
        "afr_trade_observation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_dataset_id", sa.Integer(), nullable=False),
        sa.Column("target_dsd_agency", sa.String(length=128), nullable=False),
        sa.Column("target_dsd_id", sa.String(length=255), nullable=False),
        sa.Column("target_dsd_version", sa.String(length=64), nullable=False),
        sa.Column("mapping_definition_id", sa.String(length=255), nullable=False),
        sa.Column("mapping_version", sa.String(length=64), nullable=False),
        sa.Column("freq", sa.String(length=64), nullable=False),
        sa.Column("ref_area", sa.String(length=128), nullable=False),
        sa.Column("counterpart_area", sa.String(length=128), nullable=False),
        sa.Column("trade_flow", sa.String(length=128), nullable=False),
        sa.Column("product_scheme", sa.String(length=128), nullable=False),
        sa.Column("product", sa.String(length=255), nullable=False),
        sa.Column("unit_measure", sa.String(length=128), nullable=False),
        sa.Column("time_period", sa.String(length=64), nullable=False),
        sa.Column("obs_value", sa.Numeric(), nullable=False),
        sa.Column("obs_status", sa.String(length=128), nullable=True),
        sa.Column("conf_status", sa.String(length=128), nullable=True),
        sa.Column("unit_mult", sa.String(length=32), nullable=False),
        sa.Column("decimals", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("target_key", sa.Text(), nullable=False),
        sa.Column("target_key_hash", sa.String(length=64), nullable=False),
        sa.Column("target_content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_trade_observation_id", sa.Integer(), nullable=False),
        sa.Column("first_harmonization_batch_id", sa.Integer(), nullable=False),
        sa.Column("last_harmonization_batch_id", sa.Integer(), nullable=False),
        sa.Column("mapping_trace", postgresql.JSONB(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["target_dataset_id"], ["stat_dataset.id"]),
        sa.ForeignKeyConstraint(["source_trade_observation_id"], ["trade_observation.id"]),
        sa.ForeignKeyConstraint(["first_harmonization_batch_id"], ["harmonization_batch.id"]),
        sa.ForeignKeyConstraint(["last_harmonization_batch_id"], ["harmonization_batch.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "target_dataset_id",
            "target_key_hash",
            name="uq_afr_trade_observation_dataset_target_key_hash",
        ),
    )
    for name, column in (
        ("ix_afr_trade_observation_ref_area", "ref_area"),
        ("ix_afr_trade_observation_counterpart_area", "counterpart_area"),
        ("ix_afr_trade_observation_trade_flow", "trade_flow"),
        ("ix_afr_trade_observation_product", "product"),
        ("ix_afr_trade_observation_time_period", "time_period"),
    ):
        op.create_index(name, "afr_trade_observation", [column])

    op.create_table(
        "harmonization_rejection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("harmonization_batch_id", sa.Integer(), nullable=False),
        sa.Column("source_trade_observation_id", sa.Integer(), nullable=True),
        sa.Column("source_key_hash", sa.String(length=64), nullable=True),
        sa.Column("target_key_hash", sa.String(length=64), nullable=True),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=7), nullable=False),
        sa.Column("concept_id", sa.String(length=255), nullable=True),
        sa.Column("source_value", sa.Text(), nullable=True),
        sa.Column("target_value", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("mapping_trace", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "severity IN ('WARNING', 'ERROR', 'FATAL')",
            name="ck_harmonization_rejection_severity",
        ),
        sa.ForeignKeyConstraint(
            ["harmonization_batch_id"], ["harmonization_batch.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_trade_observation_id"], ["trade_observation.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_harmonization_rejection_batch_id", "harmonization_rejection", ["harmonization_batch_id"])
    op.create_index("ix_harmonization_rejection_reason", "harmonization_rejection", ["reason_code"])


def downgrade() -> None:
    op.drop_index("ix_harmonization_rejection_reason", table_name="harmonization_rejection")
    op.drop_index("ix_harmonization_rejection_batch_id", table_name="harmonization_rejection")
    op.drop_table("harmonization_rejection")
    for name in (
        "ix_afr_trade_observation_time_period",
        "ix_afr_trade_observation_product",
        "ix_afr_trade_observation_trade_flow",
        "ix_afr_trade_observation_counterpart_area",
        "ix_afr_trade_observation_ref_area",
    ):
        op.drop_index(name, table_name="afr_trade_observation")
    op.drop_table("afr_trade_observation")
    op.drop_index("ix_harmonization_batch_status", table_name="harmonization_batch")
    op.drop_index("ix_harmonization_batch_source_dataset_id", table_name="harmonization_batch")
    op.drop_table("harmonization_batch")
