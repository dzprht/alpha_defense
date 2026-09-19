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

users = sa.Table(
    "users",
    metadata,
    sa.Column("user_id", sa.String(36), primary_key=True),
    sa.Column("profile_code", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

sessions = sa.Table(
    "sessions",
    metadata,
    sa.Column("session_id", sa.String(36), primary_key=True),
    sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
    sa.Column("manual_namespace_id", sa.String(36), nullable=False, unique=True),
    sa.Column("roles_json", sa.Text(), nullable=False),
    sa.Column("token_fingerprint", sa.String(64), nullable=False, unique=True),
    sa.Column("consent_revision", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("consent_revision >= 0", name="consent_revision_non_negative"),
    sa.CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
)

pre_sessions = sa.Table(
    "pre_sessions",
    metadata,
    sa.Column("pre_session_id", sa.String(36), primary_key=True),
    sa.Column("token_fingerprint", sa.String(64), nullable=False, unique=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column(
        "consumed_session_id",
        sa.String(36),
        sa.ForeignKey("sessions.session_id"),
        nullable=True,
        unique=True,
    ),
    sa.CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
)

consents = sa.Table(
    "consents",
    metadata,
    sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), primary_key=True),
    sa.Column("scope", sa.String(64), primary_key=True),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("revision", sa.Integer(), nullable=False),
    sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "scope IN ('analyze_communications', 'analyze_resources', "
        "'use_transaction_history', 'send_notifications', 'participate_in_research')",
        name="scope_valid",
    ),
    sa.CheckConstraint("status IN ('granted', 'revoked')", name="status_valid"),
    sa.CheckConstraint("revision >= 0", name="revision_non_negative"),
)

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

threat_snapshots = sa.Table(
    "threat_snapshots",
    metadata,
    sa.Column("snapshot_id", sa.String(36), primary_key=True),
    sa.Column("version", sa.String(128), nullable=False, unique=True),
    sa.Column("source_versions_json", sa.Text(), nullable=False),
    sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
    sa.Column("record_count", sa.Integer(), nullable=False),
    sa.Column("content_sha256", sa.String(64), nullable=False),
    sa.CheckConstraint("record_count >= 0", name="record_count_non_negative"),
    sa.CheckConstraint("valid_until > published_at", name="valid_until_after_publication"),
)

threat_records = sa.Table(
    "threat_records",
    metadata,
    sa.Column(
        "snapshot_id",
        sa.String(36),
        sa.ForeignKey("threat_snapshots.snapshot_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("source", sa.String(128), primary_key=True),
    sa.Column("source_record_id", sa.String(128), primary_key=True),
    sa.Column("indicator_type", sa.String(32), nullable=False),
    sa.Column("normalized_value", sa.String(2048), nullable=False),
    sa.Column("normalization_version", sa.String(64), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("evidence_ref", sa.String(512), nullable=False),
    sa.Column("verification_source", sa.String(128), nullable=False),
    sa.UniqueConstraint(
        "snapshot_id",
        "source",
        "indicator_type",
        "normalized_value",
        name="uq_threat_records_snapshot_source_indicator",
    ),
    sa.CheckConstraint(
        "indicator_type IN ('phone', 'domain', 'url', 'wallet', "
        "'account_token', 'ip', 'pattern_id')",
        name="indicator_type_valid",
    ),
    sa.CheckConstraint(
        "status IN ('unverified', 'active', 'revoked', 'expired')",
        name="status_valid",
    ),
    sa.CheckConstraint("expires_at > first_seen_at", name="expiry_after_first_seen"),
)

sa.Index(
    "ix_threat_records_lookup",
    threat_records.c.snapshot_id,
    threat_records.c.indicator_type,
    threat_records.c.normalized_value,
    threat_records.c.status,
)

threat_registry_state = sa.Table(
    "threat_registry_state",
    metadata,
    sa.Column("state_key", sa.String(16), primary_key=True),
    sa.Column(
        "current_snapshot_id",
        sa.String(36),
        sa.ForeignKey("threat_snapshots.snapshot_id"),
        nullable=False,
        unique=True,
    ),
    sa.Column("revision", sa.Integer(), nullable=False),
    sa.CheckConstraint("state_key = 'current'", name="state_key_current"),
    sa.CheckConstraint("revision >= 0", name="revision_non_negative"),
)
