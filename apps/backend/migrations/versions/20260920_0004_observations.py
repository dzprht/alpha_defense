"""Add immutable observations, separate content, and normalized indicators.

Revision ID: 20260920_0004
Revises: 20260919_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_0004"
down_revision: str | None = "20260919_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "observations",
        sa.Column("observation_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("namespace_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("source_event_id", sa.String(length=128), nullable=False),
        sa.Column("source_event_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_ref", sa.String(length=36), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.Column("execution_mode", sa.String(length=16), nullable=False),
        sa.Column("conversation_id", sa.String(length=128), nullable=True),
        sa.Column("call_id", sa.String(length=128), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("media_refs_json", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "(kind IN ('sms', 'messenger') AND conversation_id IS NOT NULL "
            "AND call_id IS NULL AND sequence IS NULL) OR "
            "(kind = 'call_transcript' AND conversation_id IS NULL "
            "AND call_id IS NOT NULL AND sequence IS NOT NULL) OR "
            "(kind = 'web_resource' AND conversation_id IS NULL "
            "AND call_id IS NULL AND sequence IS NULL)",
            name="ck_observations_correlation_fields_valid",
        ),
        sa.CheckConstraint(
            "execution_mode IN ('mock', 'live')",
            name="ck_observations_execution_mode_valid",
        ),
        sa.CheckConstraint(
            "kind IN ('sms', 'messenger', 'call_transcript', 'web_resource')",
            name="ck_observations_kind_valid",
        ),
        sa.CheckConstraint(
            "sequence IS NULL OR sequence >= 0",
            name="ck_observations_sequence_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.user_id"],
            name="fk_observations_owner_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.session_id"],
            name="fk_observations_session_id_sessions",
        ),
        sa.PrimaryKeyConstraint("observation_id", name="pk_observations"),
        sa.UniqueConstraint("content_ref", name="uq_observations_content_ref"),
        sa.UniqueConstraint(
            "observation_id",
            "content_ref",
            name="uq_observations_id_content_ref",
        ),
        sa.UniqueConstraint(
            "namespace_id",
            "source",
            "source_event_id",
            name="uq_observations_namespace_source_event",
        ),
    )
    op.create_index(
        "ix_observations_owner_occurred",
        "observations",
        ["owner_id", "occurred_at"],
        unique=False,
    )
    op.create_table(
        "observation_content",
        sa.Column("content_ref", sa.String(length=36), nullable=False),
        sa.Column("observation_id", sa.String(length=36), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["observation_id", "content_ref"],
            ["observations.observation_id", "observations.content_ref"],
            name="fk_observation_content_observation_ref_observations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("content_ref", name="pk_observation_content"),
        sa.UniqueConstraint("observation_id", name="uq_observation_content_observation_id"),
    )
    op.create_table(
        "observation_indicators",
        sa.Column("observation_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("indicator_type", sa.String(length=16), nullable=False),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("raw_value", sa.String(length=2048), nullable=False),
        sa.Column("normalized_value", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "indicator_type IN ('phone', 'url', 'domain')",
            name="ck_observation_indicators_type_valid",
        ),
        sa.CheckConstraint(
            "ordinal >= 0 AND ordinal < 50",
            name="ck_observation_indicators_ordinal_valid",
        ),
        sa.CheckConstraint(
            "origin IN ('sender', 'caller', 'embedded_text', 'resource_url', 'resource_domain')",
            name="ck_observation_indicators_origin_valid",
        ),
        sa.CheckConstraint(
            "status IN ('normalized', 'invalid')",
            name="ck_observation_indicators_status_valid",
        ),
        sa.CheckConstraint(
            "(status = 'normalized' AND normalized_value IS NOT NULL) OR "
            "(status = 'invalid' AND normalized_value IS NULL)",
            name="ck_observation_indicators_status_value_valid",
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"],
            ["observations.observation_id"],
            name="fk_observation_indicators_observation_id_observations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "observation_id",
            "ordinal",
            name="pk_observation_indicators",
        ),
    )
    op.create_index(
        "ix_observation_indicators_lookup",
        "observation_indicators",
        ["indicator_type", "normalized_value", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_observation_indicators_lookup", table_name="observation_indicators")
    op.drop_table("observation_indicators")
    op.drop_table("observation_content")
    op.drop_index("ix_observations_owner_occurred", table_name="observations")
    op.drop_table("observations")
