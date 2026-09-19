"""Add immutable threat registry snapshots and current pointer.

Revision ID: 20260919_0003
Revises: 20260918_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260919_0003"
down_revision: str | None = "20260918_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "threat_snapshots",
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("source_versions_json", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "record_count >= 0",
            name="ck_threat_snapshots_record_count_non_negative",
        ),
        sa.CheckConstraint(
            "valid_until > published_at",
            name="ck_threat_snapshots_valid_until_after_publication",
        ),
        sa.PrimaryKeyConstraint("snapshot_id", name="pk_threat_snapshots"),
        sa.UniqueConstraint("version", name="uq_threat_snapshots_version"),
    )
    op.create_table(
        "threat_records",
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("source_record_id", sa.String(length=128), nullable=False),
        sa.Column("indicator_type", sa.String(length=32), nullable=False),
        sa.Column("normalized_value", sa.String(length=2048), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_ref", sa.String(length=512), nullable=False),
        sa.Column("verification_source", sa.String(length=128), nullable=False),
        sa.CheckConstraint(
            "expires_at > first_seen_at",
            name="ck_threat_records_expiry_after_first_seen",
        ),
        sa.CheckConstraint(
            "indicator_type IN ('phone', 'domain', 'url', 'wallet', "
            "'account_token', 'ip', 'pattern_id')",
            name="ck_threat_records_indicator_type_valid",
        ),
        sa.CheckConstraint(
            "status IN ('unverified', 'active', 'revoked', 'expired')",
            name="ck_threat_records_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["threat_snapshots.snapshot_id"],
            name="fk_threat_records_snapshot_id_threat_snapshots",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "snapshot_id",
            "source",
            "source_record_id",
            name="pk_threat_records",
        ),
        sa.UniqueConstraint(
            "snapshot_id",
            "source",
            "indicator_type",
            "normalized_value",
            name="uq_threat_records_snapshot_source_indicator",
        ),
    )
    op.create_index(
        "ix_threat_records_lookup",
        "threat_records",
        ["snapshot_id", "indicator_type", "normalized_value", "status"],
        unique=False,
    )
    op.create_table(
        "threat_registry_state",
        sa.Column("state_key", sa.String(length=16), nullable=False),
        sa.Column("current_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "revision >= 0",
            name="ck_threat_registry_state_revision_non_negative",
        ),
        sa.CheckConstraint(
            "state_key = 'current'",
            name="ck_threat_registry_state_state_key_current",
        ),
        sa.ForeignKeyConstraint(
            ["current_snapshot_id"],
            ["threat_snapshots.snapshot_id"],
            name="fk_threat_registry_state_current_snapshot_id_threat_snapshots",
        ),
        sa.PrimaryKeyConstraint("state_key", name="pk_threat_registry_state"),
        sa.UniqueConstraint(
            "current_snapshot_id",
            name="uq_threat_registry_state_current_snapshot_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("threat_registry_state")
    op.drop_index("ix_threat_records_lookup", table_name="threat_records")
    op.drop_table("threat_records")
    op.drop_table("threat_snapshots")
