"""Persist immutable versioned transfer checks.

Revision ID: 20260927_0011
Revises: 20260927_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260927_0011"
down_revision: str | None = "20260927_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transfer_checks",
        sa.Column("check_id", sa.String(36), primary_key=True),
        sa.Column(
            "intent_id", sa.String(36), sa.ForeignKey("transfer_intents.intent_id"), nullable=False
        ),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("namespace_id", sa.String(36), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_transfer_checks_intent_time", "transfer_checks", ["intent_id", "checked_at"]
    )
    op.execute(
        "CREATE TRIGGER transfer_checks_no_update BEFORE UPDATE ON transfer_checks "
        "BEGIN SELECT RAISE(ABORT, 'transfer check is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER transfer_checks_no_delete BEFORE DELETE ON transfer_checks "
        "BEGIN SELECT RAISE(ABORT, 'transfer check is immutable'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER transfer_checks_no_delete")
    op.execute("DROP TRIGGER transfer_checks_no_update")
    op.drop_index("ix_transfer_checks_intent_time", table_name="transfer_checks")
    op.drop_table("transfer_checks")
