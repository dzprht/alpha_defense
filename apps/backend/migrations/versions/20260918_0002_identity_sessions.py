"""Add synthetic users, sessions, pre-sessions, and consent snapshots.

Revision ID: 20260918_0002
Revises: 20260915_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0002"
down_revision: str | None = "20260915_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("profile_code", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name="pk_users"),
    )
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("manual_namespace_id", sa.String(length=36), nullable=False),
        sa.Column("roles_json", sa.Text(), nullable=False),
        sa.Column("token_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("consent_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "consent_revision >= 0",
            name="ck_sessions_consent_revision_non_negative",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_sessions_expiry_after_creation",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name="fk_sessions_user_id_users",
        ),
        sa.PrimaryKeyConstraint("session_id", name="pk_sessions"),
        sa.UniqueConstraint(
            "manual_namespace_id",
            name="uq_sessions_manual_namespace_id",
        ),
        sa.UniqueConstraint("token_fingerprint", name="uq_sessions_token_fingerprint"),
    )
    op.create_table(
        "pre_sessions",
        sa.Column("pre_session_id", sa.String(length=36), nullable=False),
        sa.Column("token_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_session_id", sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_pre_sessions_expiry_after_creation",
        ),
        sa.ForeignKeyConstraint(
            ["consumed_session_id"],
            ["sessions.session_id"],
            name="fk_pre_sessions_consumed_session_id_sessions",
        ),
        sa.PrimaryKeyConstraint("pre_session_id", name="pk_pre_sessions"),
        sa.UniqueConstraint(
            "consumed_session_id",
            name="uq_pre_sessions_consumed_session_id",
        ),
        sa.UniqueConstraint(
            "token_fingerprint",
            name="uq_pre_sessions_token_fingerprint",
        ),
    )
    op.create_table(
        "consents",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "revision >= 0",
            name="ck_consents_revision_non_negative",
        ),
        sa.CheckConstraint(
            "scope IN ('analyze_communications', 'analyze_resources', "
            "'use_transaction_history', 'send_notifications', 'participate_in_research')",
            name="ck_consents_scope_valid",
        ),
        sa.CheckConstraint(
            "status IN ('granted', 'revoked')",
            name="ck_consents_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name="fk_consents_user_id_users",
        ),
        sa.PrimaryKeyConstraint("user_id", "scope", name="pk_consents"),
    )


def downgrade() -> None:
    op.drop_table("consents")
    op.drop_table("pre_sessions")
    op.drop_table("sessions")
    op.drop_table("users")
