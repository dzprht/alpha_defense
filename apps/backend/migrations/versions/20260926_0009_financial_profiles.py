"""Add owner-scoped synthetic profiles and immutable completed history.

Revision ID: 20260926_0009
Revises: 20260924_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260926_0009"
down_revision: str | None = "20260924_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_profiles",
        sa.Column("profile_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("namespace_id", sa.String(36), nullable=False),
        sa.Column("template_code", sa.String(64), nullable=False),
        sa.Column("template_version", sa.String(64), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("history_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("profile_id", name="pk_financial_profiles"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.user_id"], name="fk_financial_profiles_owner_id_users"
        ),
        sa.UniqueConstraint(
            "owner_id", "namespace_id", "template_code", name="uq_financial_profiles_owner_template"
        ),
        sa.CheckConstraint(
            "history_version >= 1", name="ck_financial_profiles_history_version_positive"
        ),
    )
    op.create_table(
        "completed_operations",
        sa.Column("operation_id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("recipient_code", sa.String(64), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("operation_id", name="pk_completed_operations"),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["financial_profiles.profile_id"],
            name="fk_completed_operations_profile_id_financial_profiles",
        ),
        sa.UniqueConstraint(
            "profile_id", "ordinal", name="uq_completed_operations_profile_ordinal"
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_completed_operations_ordinal_non_negative"),
        sa.CheckConstraint(
            "amount_minor BETWEEN 1 AND 100000000",
            name="ck_completed_operations_amount_minor_valid",
        ),
        sa.CheckConstraint("currency = 'RUB'", name="ck_completed_operations_currency_rub"),
    )
    op.create_index(
        "ix_completed_operations_profile_time",
        "completed_operations",
        ["profile_id", "completed_at"],
    )
    op.execute(
        "CREATE TRIGGER completed_operations_no_update "
        "BEFORE UPDATE ON completed_operations "
        "BEGIN SELECT RAISE(ABORT, 'completed history is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER completed_operations_no_delete "
        "BEFORE DELETE ON completed_operations "
        "BEGIN SELECT RAISE(ABORT, 'completed history is immutable'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER completed_operations_no_delete")
    op.execute("DROP TRIGGER completed_operations_no_update")
    op.drop_index("ix_completed_operations_profile_time", table_name="completed_operations")
    op.drop_table("completed_operations")
    op.drop_table("financial_profiles")
