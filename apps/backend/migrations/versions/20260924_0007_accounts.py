"""Add persistent accounts, login throttling and account session identity.

Revision ID: 20260924_0007
Revises: 20260924_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260924_0007"
down_revision: str | None = "20260924_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("normalized_login", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("namespace_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("consent_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name="pk_accounts"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name="fk_accounts_user_id_users"),
        sa.UniqueConstraint("normalized_login", name="uq_accounts_normalized_login"),
        sa.UniqueConstraint("namespace_id", name="uq_accounts_namespace_id"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_accounts_status_valid"),
        sa.CheckConstraint(
            "consent_revision >= 0", name="ck_accounts_consent_revision_non_negative"
        ),
    )
    op.create_table(
        "login_throttles",
        sa.Column("login_fingerprint", sa.String(64), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("login_fingerprint", name="pk_login_throttles"),
        sa.CheckConstraint("failures >= 0", name="ck_login_throttles_failures_non_negative"),
        sa.CheckConstraint("revision >= 0", name="ck_login_throttles_revision_non_negative"),
    )
    # ADD COLUMN preserves populated sessions referenced by other tables.
    op.add_column(
        "sessions", sa.Column("auth_kind", sa.String(16), nullable=False, server_default="demo")
    )
    op.add_column("sessions", sa.Column("workspace_namespace_id", sa.String(36), nullable=True))
    op.add_column("sessions", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "revoked_at")
    op.drop_column("sessions", "workspace_namespace_id")
    op.drop_column("sessions", "auth_kind")
    op.drop_table("login_throttles")
    op.drop_table("accounts")
