"""Persist immutable risk assessments for contact history.

Revision ID: 20260924_0008
Revises: 20260924_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260924_0008"
down_revision: str | None = "20260924_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assessments",
        sa.Column("assessment_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("namespace_id", sa.String(36), nullable=False),
        sa.Column("target_kind", sa.String(16), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("assessment_id", name="pk_assessments"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.user_id"], name="fk_assessments_owner_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.session_id"], name="fk_assessments_session_id_sessions"
        ),
        sa.CheckConstraint(
            "target_kind IN ('observation', 'transfer')", name="ck_assessments_target_kind_valid"
        ),
        sa.CheckConstraint("context_version >= 1", name="ck_assessments_context_version_positive"),
    )
    op.create_index(
        "ix_assessments_observation_history",
        "assessments",
        ["owner_id", "namespace_id", "target_id", "assessed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_assessments_observation_history", table_name="assessments")
    op.drop_table("assessments")
