"""add statistical warehouse and observation identity

Revision ID: d5e6f7a8b9c0
Revises: 9c341cb786a2
Create Date: 2026-09-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "9c341cb786a2"
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
        "stat_dataset",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agency", sa.String(length=128), nullable=False),
        sa.Column("dataflow_id", sa.String(length=255), nullable=False),
        sa.Column("dataflow_version", sa.String(length=64), nullable=False),
        sa.Column("dsd_agency", sa.String(length=128), nullable=False),
        sa.Column("dsd_id", sa.String(length=255), nullable=False),
        sa.Column("dsd_version", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=1024), nullable=False),
        sa.Column("source_system", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agency",
            "dataflow_id",
            "dataflow_version",
            name="uq_stat_dataset_source_identity",
        ),
    )

    op.create_table(
        "ingestion_batch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.String(length=128), nullable=False),
        sa.Column("query_key", sa.String(length=1024), nullable=True),
        sa.Column("query_parameters", postgresql.JSONB(), nullable=True),
        sa.Column("start_period", sa.String(length=64), nullable=True),
        sa.Column("end_period", sa.String(length=64), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=7),
            server_default=sa.text("'RUNNING'"),
            nullable=False,
        ),
        sa.Column(
            "observations_received", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "observations_parsed", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "observations_accepted", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "observations_inserted", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "observations_updated", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "observations_skipped", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "observations_rejected", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("raw_response_checksum", sa.String(length=64), nullable=True),
        sa.Column("statistical_content_checksum", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'SUCCESS', 'PARTIAL', 'FAILED')",
            name="ck_ingestion_batch_status",
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["stat_dataset.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ingestion_batch_dataset_id", "ingestion_batch", ["dataset_id"]
    )
    op.create_index("ix_ingestion_batch_status", "ingestion_batch", ["status"])

    op.create_table(
        "trade_observation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("reference_area_source_code", sa.String(length=128), nullable=False),
        sa.Column("reference_geo_id", sa.Integer(), nullable=False),
        sa.Column("counterpart_area_source_code", sa.String(length=128), nullable=True),
        sa.Column("counterpart_geo_id", sa.Integer(), nullable=True),
        sa.Column("trade_flow_code", sa.String(length=128), nullable=True),
        sa.Column("frequency_code", sa.String(length=64), nullable=True),
        sa.Column("commodity_code", sa.String(length=255), nullable=True),
        sa.Column("commodity_classification", sa.String(length=128), nullable=True),
        sa.Column("commodity_sdmx_code", sa.String(length=255), nullable=True),
        sa.Column("time_period", sa.String(length=64), nullable=True),
        sa.Column("primary_value", sa.Numeric(), nullable=True),
        sa.Column("quantity", sa.Numeric(), nullable=True),
        sa.Column("net_weight", sa.Numeric(), nullable=True),
        sa.Column("gross_weight", sa.Numeric(), nullable=True),
        sa.Column("cif_value", sa.Numeric(), nullable=True),
        sa.Column("fob_value", sa.Numeric(), nullable=True),
        sa.Column("source_dimensions", postgresql.JSONB(), nullable=False),
        sa.Column("source_attributes", postgresql.JSONB(), nullable=False),
        sa.Column("source_fields", postgresql.JSONB(), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("source_key_hash", sa.String(length=64), nullable=False),
        sa.Column("observation_content_hash", sa.String(length=64), nullable=False),
        sa.Column("first_ingestion_batch_id", sa.Integer(), nullable=False),
        sa.Column("last_ingestion_batch_id", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["counterpart_geo_id"], ["geo_area.id"]),
        sa.ForeignKeyConstraint(
            ["first_ingestion_batch_id"], ["ingestion_batch.id"]
        ),
        sa.ForeignKeyConstraint(
            ["last_ingestion_batch_id"], ["ingestion_batch.id"]
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["stat_dataset.id"]),
        sa.ForeignKeyConstraint(["reference_geo_id"], ["geo_area.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_id",
            "source_key_hash",
            name="uq_trade_observation_dataset_source_key_hash",
        ),
    )
    for name, columns in (
        ("ix_trade_observation_dataset_id", ["dataset_id"]),
        ("ix_trade_observation_reference_geo_id", ["reference_geo_id"]),
        ("ix_trade_observation_counterpart_geo_id", ["counterpart_geo_id"]),
        ("ix_trade_observation_trade_flow_code", ["trade_flow_code"]),
        ("ix_trade_observation_frequency_code", ["frequency_code"]),
        ("ix_trade_observation_commodity_code", ["commodity_code"]),
        ("ix_trade_observation_time_period", ["time_period"]),
        ("ix_trade_observation_source_key_hash", ["source_key_hash"]),
        (
            "ix_trade_observation_dataset_reference_period",
            ["dataset_id", "reference_geo_id", "time_period"],
        ),
        (
            "ix_trade_observation_dataset_reference_counterpart",
            ["dataset_id", "reference_geo_id", "counterpart_geo_id"],
        ),
        (
            "ix_trade_observation_dataset_flow_period",
            ["dataset_id", "trade_flow_code", "time_period"],
        ),
    ):
        op.create_index(name, "trade_observation", columns)

    op.create_table(
        "observation_rejection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ingestion_batch_id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=True),
        sa.Column("source_key_hash", sa.String(length=64), nullable=True),
        sa.Column("concept_id", sa.String(length=255), nullable=True),
        sa.Column("invalid_value", sa.Text(), nullable=True),
        sa.Column("reason_code", sa.String(length=25), nullable=False),
        sa.Column("severity", sa.String(length=7), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("raw_observation", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reason_code IN ('MISSING_DIMENSION', 'INVALID_CODE', "
            "'INVALID_VALUE', 'UNMAPPED_REFERENCE_AREA', "
            "'UNMAPPED_COUNTERPART_AREA', 'MALFORMED_OBSERVATION')",
            name="ck_observation_rejection_reason_code",
        ),
        sa.CheckConstraint(
            "severity IN ('WARNING', 'ERROR')",
            name="ck_observation_rejection_severity",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_batch_id"], ["ingestion_batch.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_observation_rejection_ingestion_batch_id",
        "observation_rejection",
        ["ingestion_batch_id"],
    )
    op.create_index(
        "ix_observation_rejection_reason_code",
        "observation_rejection",
        ["reason_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_observation_rejection_reason_code", table_name="observation_rejection"
    )
    op.drop_index(
        "ix_observation_rejection_ingestion_batch_id",
        table_name="observation_rejection",
    )
    op.drop_table("observation_rejection")

    for name in (
        "ix_trade_observation_dataset_flow_period",
        "ix_trade_observation_dataset_reference_counterpart",
        "ix_trade_observation_dataset_reference_period",
        "ix_trade_observation_source_key_hash",
        "ix_trade_observation_time_period",
        "ix_trade_observation_commodity_code",
        "ix_trade_observation_frequency_code",
        "ix_trade_observation_trade_flow_code",
        "ix_trade_observation_counterpart_geo_id",
        "ix_trade_observation_reference_geo_id",
        "ix_trade_observation_dataset_id",
    ):
        op.drop_index(name, table_name="trade_observation")
    op.drop_table("trade_observation")

    op.drop_index("ix_ingestion_batch_status", table_name="ingestion_batch")
    op.drop_index("ix_ingestion_batch_dataset_id", table_name="ingestion_batch")
    op.drop_table("ingestion_batch")
    op.drop_table("stat_dataset")
