"""Persist synthetic transfer drafts and immutable local-bank outcomes.

Revision ID: 20260927_0010
Revises: 20260926_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260927_0010"
down_revision: str | None = "20260926_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transfer_intents",
        sa.Column("intent_id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("namespace_id", sa.String(36), nullable=False),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey("financial_profiles.profile_id"),
            nullable=False,
        ),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("recipient_code", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_transfer_intents_revision_positive"),
        sa.CheckConstraint(
            "amount_minor BETWEEN 1 AND 100000000", name="ck_transfer_intents_amount_minor_valid"
        ),
        sa.CheckConstraint("currency = 'RUB'", name="ck_transfer_intents_currency_rub"),
        sa.CheckConstraint(
            "status IN ('draft', 'checked', 'executed', 'cancelled')",
            name="ck_transfer_intents_status_valid",
        ),
    )
    op.create_index(
        "ix_transfer_intents_owner_namespace_created",
        "transfer_intents",
        ["owner_id", "namespace_id", "created_at"],
    )
    op.create_table(
        "demo_bank_results",
        sa.Column("operation_id", sa.String(36), primary_key=True),
        sa.Column(
            "intent_id",
            sa.String(36),
            sa.ForeignKey("transfer_intents.intent_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("intent_revision", sa.Integer(), nullable=False),
        sa.Column("intent_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey("financial_profiles.profile_id"),
            nullable=False,
        ),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("recipient_code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "intent_revision >= 1", name="ck_demo_bank_results_intent_revision_positive"
        ),
        sa.CheckConstraint(
            "amount_minor BETWEEN 1 AND 100000000", name="ck_demo_bank_results_amount_minor_valid"
        ),
        sa.CheckConstraint("currency = 'RUB'", name="ck_demo_bank_results_currency_rub"),
        sa.CheckConstraint("status = 'executed'", name="ck_demo_bank_results_status_executed"),
    )
    op.execute(
        "CREATE TRIGGER demo_bank_results_no_update BEFORE UPDATE ON demo_bank_results "
        "BEGIN SELECT RAISE(ABORT, 'bank result is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER demo_bank_results_no_delete BEFORE DELETE ON demo_bank_results "
        "BEGIN SELECT RAISE(ABORT, 'bank result is immutable'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER demo_bank_results_no_delete")
    op.execute("DROP TRIGGER demo_bank_results_no_update")
    op.drop_table("demo_bank_results")
    op.drop_index("ix_transfer_intents_owner_namespace_created", table_name="transfer_intents")
    op.drop_table("transfer_intents")
