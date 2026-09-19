"""SQLite persistence for immutable threat snapshots and one atomic current pointer."""

from __future__ import annotations

import json
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult, Result, RowMapping
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from alpha_defense.application.shared import ServiceUnavailableError, StaleRevisionError
from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.threats import (
    IndicatorType,
    RegistrySnapshot,
    SourceVersion,
    ThreatIndicator,
    ThreatRecord,
    ThreatRecordStatus,
)
from alpha_defense.infrastructure.persistence.sqlalchemy.mappers import as_utc, dump_json
from alpha_defense.infrastructure.persistence.sqlalchemy.schema import (
    threat_records,
    threat_registry_state,
    threat_snapshots,
)


class SqlAlchemyThreatRegistryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_current(self) -> RegistrySnapshot | None:
        snapshot_id = _execute(
            self._session,
            sa.select(threat_registry_state.c.current_snapshot_id).where(
                threat_registry_state.c.state_key == "current"
            ),
        ).scalar_one_or_none()
        return None if snapshot_id is None else self._get_by_id(snapshot_id)

    def get_by_version(self, version: str) -> RegistrySnapshot | None:
        row = (
            _execute(
                self._session,
                sa.select(threat_snapshots).where(threat_snapshots.c.version == version),
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else self._snapshot_from_row(row)

    def publish(
        self,
        snapshot: RegistrySnapshot,
        *,
        expected_current_id: EntityId | None,
    ) -> RegistrySnapshot:
        existing = self.get_by_version(snapshot.version)
        if existing is not None:
            if not existing.has_same_content(snapshot):
                raise ValueError("registry version already exists with different content")
            return existing
        current = self.get_current()
        current_id = None if current is None else current.snapshot_id
        if current_id != expected_current_id:
            raise StaleRevisionError("current threat snapshot changed concurrently")

        _execute(self._session, sa.insert(threat_snapshots).values(_snapshot_values(snapshot)))
        if snapshot.records:
            _execute(
                self._session,
                sa.insert(threat_records).values(
                    [_record_values(snapshot.snapshot_id, record) for record in snapshot.records]
                ),
            )
        if current is None:
            result = _execute(
                self._session,
                sqlite_insert(threat_registry_state)
                .values(
                    state_key="current",
                    current_snapshot_id=str(snapshot.snapshot_id),
                    revision=0,
                )
                .on_conflict_do_nothing(index_elements=["state_key"]),
            )
        else:
            result = _execute(
                self._session,
                sa.update(threat_registry_state)
                .where(
                    threat_registry_state.c.state_key == "current",
                    threat_registry_state.c.current_snapshot_id == str(expected_current_id),
                )
                .values(
                    current_snapshot_id=str(snapshot.snapshot_id),
                    revision=threat_registry_state.c.revision + 1,
                ),
            )
        if _rowcount(result) != 1:
            raise StaleRevisionError("current threat snapshot changed concurrently")
        return snapshot

    def list_versions(self) -> tuple[str, ...]:
        rows = _execute(
            self._session,
            sa.select(threat_snapshots.c.version).order_by(threat_snapshots.c.version),
        )
        return tuple(rows.scalars())

    def _get_by_id(self, snapshot_id: str) -> RegistrySnapshot | None:
        row = (
            _execute(
                self._session,
                sa.select(threat_snapshots).where(threat_snapshots.c.snapshot_id == snapshot_id),
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else self._snapshot_from_row(row)

    def _snapshot_from_row(self, row: RowMapping) -> RegistrySnapshot:
        record_rows = _execute(
            self._session,
            sa.select(threat_records)
            .where(threat_records.c.snapshot_id == row["snapshot_id"])
            .order_by(threat_records.c.source, threat_records.c.source_record_id),
        ).mappings()
        records = tuple(_record_from_row(record) for record in record_rows)
        if len(records) != row["record_count"]:
            raise ServiceUnavailableError("Persisted threat snapshot is incomplete")
        return RegistrySnapshot(
            snapshot_id=EntityId.from_string(row["snapshot_id"]),
            version=row["version"],
            source_versions=_source_versions(row["source_versions_json"]),
            published_at=as_utc(row["published_at"]),
            valid_until=as_utc(row["valid_until"]),
            records=records,
            content_sha256=row["content_sha256"],
        )


def _snapshot_values(snapshot: RegistrySnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": str(snapshot.snapshot_id),
        "version": snapshot.version,
        "source_versions_json": dump_json(
            [{"source": item.source, "version": item.version} for item in snapshot.source_versions]
        ),
        "published_at": snapshot.published_at,
        "valid_until": snapshot.valid_until,
        "record_count": snapshot.record_count,
        "content_sha256": snapshot.content_sha256,
    }


def _record_values(snapshot_id: EntityId, record: ThreatRecord) -> dict[str, Any]:
    return {
        "snapshot_id": str(snapshot_id),
        "source": record.source,
        "source_record_id": record.source_record_id,
        "indicator_type": record.indicator.indicator_type.value,
        "normalized_value": record.indicator.normalized_value,
        "normalization_version": record.indicator.normalization_version,
        "status": record.status.value,
        "first_seen_at": record.first_seen_at,
        "observed_at": record.observed_at,
        "expires_at": record.expires_at,
        "evidence_ref": record.evidence_ref,
        "verification_source": record.verification_source,
    }


def _record_from_row(row: RowMapping) -> ThreatRecord:
    return ThreatRecord(
        source=row["source"],
        source_record_id=row["source_record_id"],
        indicator=ThreatIndicator(
            indicator_type=IndicatorType(row["indicator_type"]),
            normalized_value=row["normalized_value"],
            normalization_version=row["normalization_version"],
        ),
        status=ThreatRecordStatus(row["status"]),
        first_seen_at=as_utc(row["first_seen_at"]),
        observed_at=as_utc(row["observed_at"]),
        expires_at=as_utc(row["expires_at"]),
        evidence_ref=row["evidence_ref"],
        verification_source=row["verification_source"],
    )


def _source_versions(value: str) -> tuple[SourceVersion, ...]:
    decoded: object = json.loads(value)
    if not isinstance(decoded, list):
        raise ServiceUnavailableError("Persisted source versions are invalid")
    result: list[SourceVersion] = []
    for item in decoded:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("source"), str)
            or not isinstance(item.get("version"), str)
        ):
            raise ServiceUnavailableError("Persisted source versions are invalid")
        result.append(SourceVersion(item["source"], item["version"]))
    return tuple(result)


def _rowcount(result: Result[Any]) -> int:
    return cast(CursorResult[Any], result).rowcount


def _execute(session: Session, statement: Any) -> Result[Any]:
    try:
        return session.execute(statement)
    except IntegrityError as exc:
        raise ValueError("persistence constraint rejected the threat snapshot") from exc
    except SQLAlchemyError as exc:
        raise ServiceUnavailableError("Local persistence is unavailable") from exc
