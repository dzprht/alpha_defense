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

observations = sa.Table(
    "observations",
    metadata,
    sa.Column("observation_id", sa.String(36), primary_key=True),
    sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
    sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.session_id"), nullable=False),
    sa.Column("namespace_id", sa.String(36), nullable=False),
    sa.Column("kind", sa.String(32), nullable=False),
    sa.Column("source", sa.String(128), nullable=False),
    sa.Column("source_event_id", sa.String(128), nullable=False),
    sa.Column("source_event_fingerprint", sa.String(64), nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("content_ref", sa.String(36), nullable=False, unique=True),
    sa.Column("normalization_version", sa.String(64), nullable=False),
    sa.Column("execution_mode", sa.String(16), nullable=False),
    sa.Column("conversation_id", sa.String(128), nullable=True),
    sa.Column("call_id", sa.String(128), nullable=True),
    sa.Column("sequence", sa.Integer(), nullable=True),
    sa.Column("media_refs_json", sa.Text(), nullable=False),
    sa.UniqueConstraint(
        "namespace_id",
        "source",
        "source_event_id",
        name="uq_observations_namespace_source_event",
    ),
    sa.UniqueConstraint(
        "observation_id",
        "content_ref",
        name="uq_observations_id_content_ref",
    ),
    sa.CheckConstraint(
        "kind IN ('sms', 'messenger', 'call_transcript', 'web_resource')",
        name="kind_valid",
    ),
    sa.CheckConstraint("execution_mode IN ('mock', 'live')", name="execution_mode_valid"),
    sa.CheckConstraint("sequence IS NULL OR sequence >= 0", name="sequence_non_negative"),
    sa.CheckConstraint(
        "(kind IN ('sms', 'messenger') AND conversation_id IS NOT NULL "
        "AND call_id IS NULL AND sequence IS NULL) OR "
        "(kind = 'call_transcript' AND conversation_id IS NULL "
        "AND call_id IS NOT NULL AND sequence IS NOT NULL) OR "
        "(kind = 'web_resource' AND conversation_id IS NULL "
        "AND call_id IS NULL AND sequence IS NULL)",
        name="correlation_fields_valid",
    ),
)

sa.Index("ix_observations_owner_occurred", observations.c.owner_id, observations.c.occurred_at)

observation_content = sa.Table(
    "observation_content",
    metadata,
    sa.Column("content_ref", sa.String(36), primary_key=True),
    sa.Column("observation_id", sa.String(36), nullable=False, unique=True),
    sa.Column("payload_json", sa.Text(), nullable=False),
    sa.Column("content_sha256", sa.String(64), nullable=False),
    sa.ForeignKeyConstraint(
        ["observation_id", "content_ref"],
        ["observations.observation_id", "observations.content_ref"],
        name="fk_observation_content_observation_ref_observations",
        ondelete="CASCADE",
    ),
)

observation_indicators = sa.Table(
    "observation_indicators",
    metadata,
    sa.Column(
        "observation_id",
        sa.String(36),
        sa.ForeignKey("observations.observation_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("ordinal", sa.Integer(), primary_key=True),
    sa.Column("indicator_type", sa.String(16), nullable=False),
    sa.Column("origin", sa.String(32), nullable=False),
    sa.Column("raw_value", sa.String(2048), nullable=False),
    sa.Column("normalized_value", sa.String(2048), nullable=True),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("normalization_version", sa.String(64), nullable=False),
    sa.CheckConstraint("ordinal >= 0 AND ordinal < 50", name="ordinal_valid"),
    sa.CheckConstraint("indicator_type IN ('phone', 'url', 'domain')", name="type_valid"),
    sa.CheckConstraint(
        "origin IN ('sender', 'caller', 'embedded_text', 'resource_url', 'resource_domain')",
        name="origin_valid",
    ),
    sa.CheckConstraint("status IN ('normalized', 'invalid')", name="status_valid"),
    sa.CheckConstraint(
        "(status = 'normalized' AND normalized_value IS NOT NULL) OR "
        "(status = 'invalid' AND normalized_value IS NULL)",
        name="status_value_valid",
    ),
)

sa.Index(
    "ix_observation_indicators_lookup",
    observation_indicators.c.indicator_type,
    observation_indicators.c.normalized_value,
    observation_indicators.c.status,
)

incidents = sa.Table(
    "incidents",
    metadata,
    sa.Column("incident_id", sa.String(36), primary_key=True),
    sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
    sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.session_id"), nullable=False),
    sa.Column("namespace_id", sa.String(36), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("latest_assessment_id", sa.String(36), nullable=True),
    sa.Column("current_resolution_code", sa.String(32), nullable=True),
    sa.Column("context_version", sa.Integer(), nullable=False),
    sa.Column("revision", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("execution_mode", sa.String(16), nullable=False),
    sa.CheckConstraint("status IN ('open', 'monitoring', 'resolved')", name="status_valid"),
    sa.CheckConstraint("context_version >= 1", name="context_version_positive"),
    sa.CheckConstraint("revision >= 0", name="revision_non_negative"),
    sa.CheckConstraint("updated_at >= created_at", name="updated_after_creation"),
    sa.CheckConstraint("execution_mode IN ('mock', 'live')", name="execution_mode_valid"),
    sa.CheckConstraint(
        "(status = 'resolved' AND current_resolution_code IS NOT NULL) OR "
        "(status IN ('open', 'monitoring') AND current_resolution_code IS NULL)",
        name="resolution_status_valid",
    ),
)

sa.Index(
    "ix_incidents_scope_updated",
    incidents.c.owner_id,
    incidents.c.session_id,
    incidents.c.namespace_id,
    incidents.c.updated_at,
)

incident_observations = sa.Table(
    "incident_observations",
    metadata,
    sa.Column(
        "incident_id",
        sa.String(36),
        sa.ForeignKey("incidents.incident_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("ordinal", sa.Integer(), primary_key=True),
    sa.Column(
        "observation_id",
        sa.String(36),
        sa.ForeignKey("observations.observation_id"),
        nullable=False,
        unique=True,
    ),
    sa.Column("attached_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("context_version", sa.Integer(), nullable=False),
    sa.Column("correlation_reason", sa.String(32), nullable=False),
    sa.Column("correlation_key_kind", sa.String(16), nullable=True),
    sa.Column("correlation_key_value", sa.String(4096), nullable=True),
    sa.UniqueConstraint(
        "incident_id",
        "observation_id",
        name="uq_incident_observations_incident_observation",
    ),
    sa.UniqueConstraint(
        "incident_id",
        "context_version",
        name="uq_incident_observations_context_version",
    ),
    sa.CheckConstraint("ordinal >= 0", name="ordinal_non_negative"),
    sa.CheckConstraint("context_version >= 1", name="context_version_positive"),
    sa.CheckConstraint(
        "correlation_reason IN ('new_incident', 'conversation', 'call', 'indicator')",
        name="correlation_reason_valid",
    ),
    sa.CheckConstraint(
        "(correlation_reason = 'new_incident' AND correlation_key_kind IS NULL "
        "AND correlation_key_value IS NULL) OR "
        "(correlation_reason != 'new_incident' AND correlation_key_kind IS NOT NULL "
        "AND correlation_key_value IS NOT NULL)",
        name="correlation_key_presence_valid",
    ),
    sa.CheckConstraint(
        "correlation_key_kind IS NULL OR "
        "correlation_key_kind IN ('conversation', 'call', 'indicator')",
        name="correlation_key_kind_valid",
    ),
)

incident_correlation_keys = sa.Table(
    "incident_correlation_keys",
    metadata,
    sa.Column("incident_id", sa.String(36), primary_key=True),
    sa.Column("observation_id", sa.String(36), primary_key=True),
    sa.Column("key_kind", sa.String(16), primary_key=True),
    sa.Column("key_value", sa.String(4096), primary_key=True),
    sa.ForeignKeyConstraint(
        ["incident_id", "observation_id"],
        ["incident_observations.incident_id", "incident_observations.observation_id"],
        name="fk_incident_correlation_keys_observation",
        ondelete="CASCADE",
    ),
    sa.CheckConstraint(
        "key_kind IN ('conversation', 'call', 'indicator')",
        name="key_kind_valid",
    ),
)

sa.Index(
    "ix_incident_correlation_keys_lookup",
    incident_correlation_keys.c.key_kind,
    incident_correlation_keys.c.key_value,
    incident_correlation_keys.c.incident_id,
)

incident_assessments = sa.Table(
    "incident_assessments",
    metadata,
    sa.Column(
        "incident_id",
        sa.String(36),
        sa.ForeignKey("incidents.incident_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("ordinal", sa.Integer(), primary_key=True),
    sa.Column("assessment_id", sa.String(36), nullable=False, unique=True),
    sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("context_version", sa.Integer(), nullable=False),
    sa.CheckConstraint("ordinal >= 0", name="ordinal_non_negative"),
    sa.CheckConstraint("context_version >= 1", name="context_version_positive"),
)

incident_resolutions = sa.Table(
    "incident_resolutions",
    metadata,
    sa.Column(
        "incident_id",
        sa.String(36),
        sa.ForeignKey("incidents.incident_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("ordinal", sa.Integer(), primary_key=True),
    sa.Column("resolution_code", sa.String(32), nullable=False),
    sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("resolved_by", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
    sa.Column("context_version", sa.Integer(), nullable=False),
    sa.CheckConstraint("ordinal >= 0", name="ordinal_non_negative"),
    sa.CheckConstraint("context_version >= 1", name="context_version_positive"),
    sa.CheckConstraint(
        "resolution_code IN ('user_cancelled', 'false_positive_reported', "
        "'no_action_needed', 'transferred_to_support')",
        name="resolution_code_valid",
    ),
)

namespace_risk_states = sa.Table(
    "namespace_risk_states",
    metadata,
    sa.Column("namespace_id", sa.String(36), primary_key=True),
    sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
    sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.session_id"), nullable=False),
    sa.Column("ingress_risk_epoch", sa.Integer(), nullable=False),
    sa.Column("revision", sa.Integer(), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("execution_mode", sa.String(16), nullable=False),
    sa.CheckConstraint("ingress_risk_epoch >= 1", name="ingress_risk_epoch_positive"),
    sa.CheckConstraint("revision >= 0", name="revision_non_negative"),
    sa.CheckConstraint("execution_mode IN ('mock', 'live')", name="execution_mode_valid"),
)

namespace_pending_analyses = sa.Table(
    "namespace_pending_analyses",
    metadata,
    sa.Column(
        "namespace_id",
        sa.String(36),
        sa.ForeignKey("namespace_risk_states.namespace_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "observation_id",
        sa.String(36),
        sa.ForeignKey("observations.observation_id"),
        primary_key=True,
        unique=True,
    ),
    sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.incident_id"), nullable=False),
    sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
)

warnings = sa.Table(
    "warnings",
    metadata,
    sa.Column("warning_id", sa.String(36), primary_key=True),
    sa.Column("assessment_id", sa.String(36), nullable=False, unique=True),
    sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
    sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.session_id"), nullable=False),
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
    sa.CheckConstraint("context_version >= 1", name="context_version_positive"),
    sa.CheckConstraint("revision >= 0", name="revision_non_negative"),
    sa.CheckConstraint("target_kind IN ('observation', 'transfer')", name="target_kind_valid"),
    sa.CheckConstraint(
        "severity IN ('low', 'medium', 'high', 'critical', 'unknown')",
        name="severity_valid",
    ),
    sa.CheckConstraint(
        "completeness IN ('complete', 'partial', 'unavailable')",
        name="completeness_valid",
    ),
    sa.CheckConstraint("execution_mode IN ('mock', 'live')", name="execution_mode_valid"),
    sa.CheckConstraint(
        "(dispatched_at IS NULL OR dispatched_at >= created_at) AND "
        "(presented_at IS NULL OR (dispatched_at IS NOT NULL AND "
        "presented_at >= dispatched_at)) AND "
        "(responded_at IS NULL OR (presented_at IS NOT NULL AND responded_at >= presented_at))",
        name="lifecycle_order_valid",
    ),
    sa.CheckConstraint(
        "(responded_at IS NULL AND response IS NULL AND selected_action_code IS NULL) OR "
        "(responded_at IS NOT NULL AND response IN ('acknowledged', 'dismissed') "
        "AND selected_action_code IS NULL) OR "
        "(responded_at IS NOT NULL AND response = 'action_selected' "
        "AND selected_action_code IS NOT NULL)",
        name="response_valid",
    ),
)

sa.Index(
    "ix_warnings_inbox",
    warnings.c.owner_id,
    warnings.c.session_id,
    warnings.c.namespace_id,
    warnings.c.dispatched_at,
)
