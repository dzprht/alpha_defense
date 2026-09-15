"""SQLAlchemy Core schema mirrored by the Alembic technical migration."""

import sqlalchemy as sa

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)

idempotency_records = sa.Table(
    "idempotency_records",
    metadata,
    sa.Column("record_id", sa.String(36), primary_key=True),
    sa.Column("principal_fingerprint", sa.String(64), nullable=False),
    sa.Column("session_id", sa.String(36), nullable=False, server_default=""),
    sa.Column("namespace_id", sa.String(36), nullable=False, server_default=""),
    sa.Column("method", sa.String(16), nullable=False),
    sa.Column("canonical_route", sa.String(255), nullable=False),
    sa.Column("idempotency_key", sa.String(255), nullable=False),
    sa.Column("command_hash", sa.String(64), nullable=False),
    sa.Column("resource_id", sa.String(36), nullable=False),
    sa.Column("state", sa.String(32), nullable=False),
    sa.Column("result_json", sa.Text(), nullable=True),
    sa.Column("revision", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "principal_fingerprint",
        "session_id",
        "namespace_id",
        "method",
        "canonical_route",
        "idempotency_key",
        name="uq_idempotency_records_command_scope",
    ),
    sa.CheckConstraint("revision >= 0", name="revision_non_negative"),
    sa.CheckConstraint(
        "(state = 'in_progress' AND result_json IS NULL) OR "
        "(state IN ('completed', 'failed') AND result_json IS NOT NULL)",
        name="state_result_valid",
    ),
)

audit_events = sa.Table(
    "audit_events",
    metadata,
    sa.Column("event_id", sa.String(36), primary_key=True),
    sa.Column("event_type", sa.String(128), nullable=False),
    sa.Column("schema_version", sa.Integer(), nullable=False),
    sa.Column("aggregate_id", sa.String(36), nullable=False),
    sa.Column("aggregate_revision", sa.Integer(), nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("correlation_id", sa.String(36), nullable=False),
    sa.Column("causation_id", sa.String(36), nullable=True),
    sa.Column("execution_mode", sa.String(16), nullable=False),
    sa.Column("payload_json", sa.Text(), nullable=False),
    sa.Column("actor_id", sa.String(36), nullable=True),
    sa.Column("session_id", sa.String(36), nullable=True),
    sa.Column("namespace_id", sa.String(36), nullable=True),
    sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("schema_version = 1", name="schema_version_one"),
    sa.CheckConstraint("aggregate_revision >= 0", name="aggregate_revision_non_negative"),
    sa.CheckConstraint("execution_mode IN ('mock', 'live')", name="execution_mode_valid"),
)

outbox = sa.Table(
    "outbox",
    metadata,
    sa.Column("message_id", sa.String(36), primary_key=True),
    sa.Column("topic", sa.String(128), nullable=False),
    sa.Column("event_id", sa.String(36), nullable=False),
    sa.Column("event_type", sa.String(128), nullable=False),
    sa.Column("schema_version", sa.Integer(), nullable=False),
    sa.Column("aggregate_id", sa.String(36), nullable=False),
    sa.Column("aggregate_revision", sa.Integer(), nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("correlation_id", sa.String(36), nullable=False),
    sa.Column("causation_id", sa.String(36), nullable=True),
    sa.Column("execution_mode", sa.String(16), nullable=False),
    sa.Column("payload_json", sa.Text(), nullable=False),
    sa.Column("state", sa.String(32), nullable=False),
    sa.Column("attempts", sa.Integer(), nullable=False),
    sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("last_error_code", sa.String(64), nullable=True),
    sa.Column("revision", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("event_id", "topic", name="uq_outbox_event_topic"),
    sa.CheckConstraint("schema_version = 1", name="schema_version_one"),
    sa.CheckConstraint("aggregate_revision >= 0", name="aggregate_revision_non_negative"),
    sa.CheckConstraint("attempts >= 0", name="attempts_non_negative"),
    sa.CheckConstraint("revision >= 0", name="revision_non_negative"),
    sa.CheckConstraint("execution_mode IN ('mock', 'live')", name="execution_mode_valid"),
    sa.CheckConstraint(
        "(state = 'pending' AND lease_expires_at IS NULL AND delivered_at IS NULL) OR "
        "(state = 'processing' AND lease_expires_at IS NOT NULL AND delivered_at IS NULL) OR "
        "(state = 'delivered' AND lease_expires_at IS NULL AND delivered_at IS NOT NULL)",
        name="state_timestamps_valid",
    ),
)

sa.Index("ix_outbox_dispatch", outbox.c.state, outbox.c.next_attempt_at, outbox.c.created_at)
