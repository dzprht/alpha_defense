"""Create idempotency, immutable audit, and durable outbox tables.

Revision ID: 20260915_0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("principal_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=36), server_default="", nullable=False),
        sa.Column("namespace_id", sa.String(length=36), server_default="", nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("canonical_route", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("command_hash", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ck_idempotency_records_revision_non_negative"),
        sa.CheckConstraint(
            "(state = 'in_progress' AND result_json IS NULL) OR "
            "(state IN ('completed', 'failed') AND result_json IS NOT NULL)",
            name="ck_idempotency_records_state_result_valid",
        ),
        sa.PrimaryKeyConstraint("record_id", name="pk_idempotency_records"),
        sa.UniqueConstraint(
            "principal_fingerprint",
            "session_id",
            "namespace_id",
            "method",
            "canonical_route",
            "idempotency_key",
            name="uq_idempotency_records_command_scope",
        ),
    )
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("aggregate_id", sa.String(length=36), nullable=False),
        sa.Column("aggregate_revision", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("causation_id", sa.String(length=36), nullable=True),
        sa.Column("execution_mode", sa.String(length=16), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("namespace_id", sa.String(length=36), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "aggregate_revision >= 0",
            name="ck_audit_events_aggregate_revision_non_negative",
        ),
        sa.CheckConstraint("schema_version = 1", name="ck_audit_events_schema_version_one"),
        sa.CheckConstraint(
            "execution_mode IN ('mock', 'live')",
            name="ck_audit_events_execution_mode_valid",
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_audit_events"),
    )
    op.create_table(
        "outbox",
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("topic", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("aggregate_id", sa.String(length=36), nullable=False),
        sa.Column("aggregate_revision", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("causation_id", sa.String(length=36), nullable=True),
        sa.Column("execution_mode", sa.String(length=16), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "aggregate_revision >= 0",
            name="ck_outbox_aggregate_revision_non_negative",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_outbox_attempts_non_negative"),
        sa.CheckConstraint(
            "execution_mode IN ('mock', 'live')",
            name="ck_outbox_execution_mode_valid",
        ),
        sa.CheckConstraint("revision >= 0", name="ck_outbox_revision_non_negative"),
        sa.CheckConstraint("schema_version = 1", name="ck_outbox_schema_version_one"),
        sa.CheckConstraint(
            "(state = 'pending' AND lease_expires_at IS NULL AND delivered_at IS NULL) OR "
            "(state = 'processing' AND lease_expires_at IS NOT NULL "
            "AND delivered_at IS NULL) OR "
            "(state = 'delivered' AND lease_expires_at IS NULL AND delivered_at IS NOT NULL)",
            name="ck_outbox_state_timestamps_valid",
        ),
        sa.PrimaryKeyConstraint("message_id", name="pk_outbox"),
        sa.UniqueConstraint("event_id", "topic", name="uq_outbox_event_topic"),
    )
    op.create_index(
        "ix_outbox_dispatch",
        "outbox",
        ["state", "next_attempt_at", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_dispatch", table_name="outbox")
    op.drop_table("outbox")
    op.drop_table("audit_events")
    op.drop_table("idempotency_records")
