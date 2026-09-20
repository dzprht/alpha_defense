"""Add incidents, timeline links, and namespace risk freshness.

Revision ID: 20260920_0005
Revises: 20260920_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_0005"
down_revision: str | None = "20260920_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("namespace_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("latest_assessment_id", sa.String(length=36), nullable=True),
        sa.Column("current_resolution_code", sa.String(length=32), nullable=True),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("execution_mode", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "context_version >= 1",
            name="ck_incidents_context_version_positive",
        ),
        sa.CheckConstraint(
            "execution_mode IN ('mock', 'live')",
            name="ck_incidents_execution_mode_valid",
        ),
        sa.CheckConstraint("revision >= 0", name="ck_incidents_revision_non_negative"),
        sa.CheckConstraint(
            "(status = 'resolved' AND current_resolution_code IS NOT NULL) OR "
            "(status IN ('open', 'monitoring') AND current_resolution_code IS NULL)",
            name="ck_incidents_resolution_status_valid",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'monitoring', 'resolved')",
            name="ck_incidents_status_valid",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_incidents_updated_after_creation",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.user_id"],
            name="fk_incidents_owner_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.session_id"],
            name="fk_incidents_session_id_sessions",
        ),
        sa.PrimaryKeyConstraint("incident_id", name="pk_incidents"),
    )
    op.create_index(
        "ix_incidents_scope_updated",
        "incidents",
        ["owner_id", "session_id", "namespace_id", "updated_at"],
        unique=False,
    )
    op.create_table(
        "incident_observations",
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("observation_id", sa.String(length=36), nullable=False),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("correlation_reason", sa.String(length=32), nullable=False),
        sa.Column("correlation_key_kind", sa.String(length=16), nullable=True),
        sa.Column("correlation_key_value", sa.String(length=4096), nullable=True),
        sa.CheckConstraint(
            "context_version >= 1",
            name="ck_incident_observations_context_version_positive",
        ),
        sa.CheckConstraint(
            "correlation_key_kind IS NULL OR "
            "correlation_key_kind IN ('conversation', 'call', 'indicator')",
            name="ck_incident_observations_correlation_key_kind_valid",
        ),
        sa.CheckConstraint(
            "(correlation_reason = 'new_incident' AND correlation_key_kind IS NULL "
            "AND correlation_key_value IS NULL) OR "
            "(correlation_reason != 'new_incident' AND correlation_key_kind IS NOT NULL "
            "AND correlation_key_value IS NOT NULL)",
            name="ck_incident_observations_correlation_key_presence_valid",
        ),
        sa.CheckConstraint(
            "correlation_reason IN ('new_incident', 'conversation', 'call', 'indicator')",
            name="ck_incident_observations_correlation_reason_valid",
        ),
        sa.CheckConstraint(
            "ordinal >= 0",
            name="ck_incident_observations_ordinal_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.incident_id"],
            name="fk_incident_observations_incident_id_incidents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"],
            ["observations.observation_id"],
            name="fk_incident_observations_observation_id_observations",
        ),
        sa.PrimaryKeyConstraint(
            "incident_id",
            "ordinal",
            name="pk_incident_observations",
        ),
        sa.UniqueConstraint(
            "incident_id",
            "context_version",
            name="uq_incident_observations_context_version",
        ),
        sa.UniqueConstraint(
            "incident_id",
            "observation_id",
            name="uq_incident_observations_incident_observation",
        ),
        sa.UniqueConstraint(
            "observation_id",
            name="uq_incident_observations_observation_id",
        ),
    )
    op.create_table(
        "incident_correlation_keys",
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("observation_id", sa.String(length=36), nullable=False),
        sa.Column("key_kind", sa.String(length=16), nullable=False),
        sa.Column("key_value", sa.String(length=4096), nullable=False),
        sa.CheckConstraint(
            "key_kind IN ('conversation', 'call', 'indicator')",
            name="ck_incident_correlation_keys_key_kind_valid",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id", "observation_id"],
            ["incident_observations.incident_id", "incident_observations.observation_id"],
            name="fk_incident_correlation_keys_observation",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "incident_id",
            "observation_id",
            "key_kind",
            "key_value",
            name="pk_incident_correlation_keys",
        ),
    )
    op.create_index(
        "ix_incident_correlation_keys_lookup",
        "incident_correlation_keys",
        ["key_kind", "key_value", "incident_id"],
        unique=False,
    )
    op.create_table(
        "incident_assessments",
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "context_version >= 1",
            name="ck_incident_assessments_context_version_positive",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_incident_assessments_ordinal_non_negative"),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.incident_id"],
            name="fk_incident_assessments_incident_id_incidents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "incident_id",
            "ordinal",
            name="pk_incident_assessments",
        ),
        sa.UniqueConstraint(
            "assessment_id",
            name="uq_incident_assessments_assessment_id",
        ),
    )
    op.create_table(
        "incident_resolutions",
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("resolution_code", sa.String(length=32), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_by", sa.String(length=36), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "context_version >= 1",
            name="ck_incident_resolutions_context_version_positive",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_incident_resolutions_ordinal_non_negative"),
        sa.CheckConstraint(
            "resolution_code IN ('user_cancelled', 'false_positive_reported', "
            "'no_action_needed', 'transferred_to_support')",
            name="ck_incident_resolutions_resolution_code_valid",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.incident_id"],
            name="fk_incident_resolutions_incident_id_incidents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.user_id"],
            name="fk_incident_resolutions_resolved_by_users",
        ),
        sa.PrimaryKeyConstraint(
            "incident_id",
            "ordinal",
            name="pk_incident_resolutions",
        ),
    )
    op.create_table(
        "namespace_risk_states",
        sa.Column("namespace_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("ingress_risk_epoch", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("execution_mode", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "execution_mode IN ('mock', 'live')",
            name="ck_namespace_risk_states_execution_mode_valid",
        ),
        sa.CheckConstraint(
            "ingress_risk_epoch >= 1",
            name="ck_namespace_risk_states_ingress_risk_epoch_positive",
        ),
        sa.CheckConstraint(
            "revision >= 0",
            name="ck_namespace_risk_states_revision_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.user_id"],
            name="fk_namespace_risk_states_owner_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.session_id"],
            name="fk_namespace_risk_states_session_id_sessions",
        ),
        sa.PrimaryKeyConstraint("namespace_id", name="pk_namespace_risk_states"),
    )
    op.create_table(
        "namespace_pending_analyses",
        sa.Column("namespace_id", sa.String(length=36), nullable=False),
        sa.Column("observation_id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.incident_id"],
            name="fk_namespace_pending_analyses_incident_id_incidents",
        ),
        sa.ForeignKeyConstraint(
            ["namespace_id"],
            ["namespace_risk_states.namespace_id"],
            name="fk_namespace_pending_analyses_namespace_id_namespace_risk_states",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"],
            ["observations.observation_id"],
            name="fk_namespace_pending_analyses_observation_id_observations",
        ),
        sa.PrimaryKeyConstraint(
            "namespace_id",
            "observation_id",
            name="pk_namespace_pending_analyses",
        ),
        sa.UniqueConstraint(
            "observation_id",
            name="uq_namespace_pending_analyses_observation_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("namespace_pending_analyses")
    op.drop_table("namespace_risk_states")
    op.drop_table("incident_resolutions")
    op.drop_table("incident_assessments")
    op.drop_index(
        "ix_incident_correlation_keys_lookup",
        table_name="incident_correlation_keys",
    )
    op.drop_table("incident_correlation_keys")
    op.drop_table("incident_observations")
    op.drop_index("ix_incidents_scope_updated", table_name="incidents")
    op.drop_table("incidents")
