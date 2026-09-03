"""add basic trade-ingestion rejection reasons

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-09-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_REASONS = (
    "MISSING_DIMENSION",
    "INVALID_CODE",
    "INVALID_VALUE",
    "UNMAPPED_REFERENCE_AREA",
    "UNMAPPED_COUNTERPART_AREA",
    "MALFORMED_OBSERVATION",
)
NEW_REASONS = OLD_REASONS + (
    "REFERENCE_AREA_NOT_AU_MEMBER",
    "MISSING_TIME_PERIOD",
    "MISSING_PRIMARY_VALUE",
    "NORMALIZATION_ERROR",
)


def _reason_check(reasons: tuple[str, ...]) -> str:
    values = ", ".join(f"'{reason}'" for reason in reasons)
    return f"reason_code IN ({values})"


def upgrade() -> None:
    op.drop_constraint(
        "ck_observation_rejection_reason_code",
        "observation_rejection",
        type_="check",
    )
    op.alter_column(
        "observation_rejection",
        "reason_code",
        existing_type=sa.String(length=25),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_observation_rejection_reason_code",
        "observation_rejection",
        _reason_check(NEW_REASONS),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_observation_rejection_reason_code",
        "observation_rejection",
        type_="check",
    )
    op.alter_column(
        "observation_rejection",
        "reason_code",
        existing_type=sa.String(length=32),
        type_=sa.String(length=25),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_observation_rejection_reason_code",
        "observation_rejection",
        _reason_check(OLD_REASONS),
    )
