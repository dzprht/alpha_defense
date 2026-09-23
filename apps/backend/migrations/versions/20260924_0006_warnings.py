"""Persist in-app warnings separately from assessments and transfer decisions.

Revision ID: 20260924_0006
Revises: 20260920_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260924_0006"
down_revision: str | None = "20260920_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "warnings",
        sa.Column("warning_id", sa.String(36), nullable=False),
        sa.Column("assessment_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("namespace_id", sa.String(36), nullable=False),
        sa.Column("target_kind", sa.String(16), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("completeness", sa.String(16), nullable=False),
        sa.Column("risk_label", sa.String(160), nullable=False),
        sa.Column("explanation", sa.String(4000), nullable=False),
        sa.Column("content_version", sa.String(128), nullable=False),
        sa.Column("allowed_actions_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("execution_mode", sa.String(16), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("presented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response", sa.String(32), nullable=True),
        sa.Column("selected_action_code", sa.String(64), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("warning_id", name="pk_warnings"),
        sa.UniqueConstraint("assessment_id", name="uq_warnings_assessment_id"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.user_id"], name="fk_warnings_owner_id_users"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.session_id"], name="fk_warnings_session_id_sessions"
        ),
        sa.CheckConstraint("context_version >= 1", name="ck_warnings_context_version_positive"),
        sa.CheckConstraint("revision >= 0", name="ck_warnings_revision_non_negative"),
        sa.CheckConstraint(
            "target_kind IN ('observation', 'transfer')", name="ck_warnings_target_kind_valid"
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical', 'unknown')",
            name="ck_warnings_severity_valid",
        ),
        sa.CheckConstraint(
            "completeness IN ('complete', 'partial', 'unavailable')",
            name="ck_warnings_completeness_valid",
        ),
        sa.CheckConstraint(
            "execution_mode IN ('mock', 'live')", name="ck_warnings_execution_mode_valid"
        ),
        sa.CheckConstraint(
            "(dispatched_at IS NULL OR dispatched_at >= created_at) AND "
            "(presented_at IS NULL OR (dispatched_at IS NOT NULL AND "
            "presented_at >= dispatched_at)) AND "
            "(responded_at IS NULL OR (presented_at IS NOT NULL AND responded_at >= presented_at))",
            name="ck_warnings_lifecycle_order_valid",
        ),
        sa.CheckConstraint(
            "(responded_at IS NULL AND response IS NULL AND selected_action_code IS NULL) OR "
            "(responded_at IS NOT NULL AND response IN ('acknowledged', 'dismissed') "
            "AND selected_action_code IS NULL) OR "
            "(responded_at IS NOT NULL AND response = 'action_selected' "
            "AND selected_action_code IS NOT NULL)",
            name="ck_warnings_response_valid",
        ),
    )
    op.create_index(
        "ix_warnings_inbox",
        "warnings",
        ["owner_id", "session_id", "namespace_id", "dispatched_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_warnings_inbox", table_name="warnings")
    op.drop_table("warnings")
