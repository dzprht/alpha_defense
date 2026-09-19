"""Validate, normalize, and atomically publish one threat feed snapshot."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from alpha_defense.application.ports import (
    AuditRecord,
    Clock,
    EventEnvelope,
    IdGenerator,
    ThreatBatch,
    ThreatFeedPort,
    ThreatFeedUnavailableError,
    ThreatUnitOfWorkFactory,
)
from alpha_defense.application.shared import ServiceUnavailableError, ValidationError
from alpha_defense.application.threats.dto import RefreshRegistryResult
from alpha_defense.domain.shared import ExecutionMode
from alpha_defense.domain.threats import (
    NORMALIZATION_VERSION,
    IndicatorType,
    RegistrySnapshot,
    SourceVersion,
    ThreatIndicator,
    ThreatRecord,
    ThreatRecordStatus,
)


class RefreshThreatRegistry:
    def __init__(
        self,
        *,
        source: str,
        feed: ThreatFeedPort,
        unit_of_work: ThreatUnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
        execution_mode: ExecutionMode,
    ) -> None:
        self._source = source
        self._feed = feed
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._id_generator = id_generator
        self._execution_mode = execution_mode

    def execute(self) -> RefreshRegistryResult:
        try:
            batch = self._feed.fetch(self._source)
        except ThreatFeedUnavailableError as exc:
            raise ServiceUnavailableError("Threat feed is unavailable") from exc
        now = self._clock.now_utc()
        try:
            source_version = _validate_batch(batch, expected_source=self._source, now=now)
            records = tuple(sorted(_map_records(batch), key=_record_sort_key))
            content_sha256 = _snapshot_digest(source_version, batch.valid_until, records)
            snapshot = RegistrySnapshot(
                snapshot_id=self._id_generator.new_id(),
                version=(
                    f"registry-{source_version.version.replace('.', '-')}-{content_sha256[:12]}"
                ),
                source_versions=(source_version,),
                published_at=now,
                valid_until=batch.valid_until,
                records=records,
                content_sha256=content_sha256,
            )
        except ValidationError:
            raise
        except (TypeError, ValueError) as exc:
            raise ValidationError("Threat feed batch is invalid") from exc

        with self._unit_of_work() as uow:
            current = uow.threat_registry.get_current()
            if current is not None:
                current_source = _source_version(current, self._source)
                if (
                    current_source is not None
                    and source_version.precedence < current_source.precedence
                ):
                    raise ValidationError("Threat feed version must not move backwards")
                if current_source == source_version:
                    if current.content_sha256 != snapshot.content_sha256:
                        raise ValidationError("Threat feed changed without a version change")
                    return _result(current, published=False)
            stored = uow.threat_registry.publish(
                snapshot,
                expected_current_id=None if current is None else current.snapshot_id,
            )
            published = stored.snapshot_id == snapshot.snapshot_id
            if published:
                uow.audit.append(
                    AuditRecord(
                        event=EventEnvelope(
                            event_id=self._id_generator.new_id(),
                            event_type="registry.updated",
                            aggregate_id=snapshot.snapshot_id,
                            aggregate_revision=0,
                            occurred_at=now,
                            correlation_id=snapshot.snapshot_id,
                            execution_mode=self._execution_mode,
                            payload={
                                "registry_version": snapshot.version,
                                "source": source_version.source,
                                "source_version": source_version.version,
                                "record_count": snapshot.record_count,
                                "content_sha256": snapshot.content_sha256,
                            },
                        ),
                        recorded_at=now,
                    )
                )
            uow.commit()
        return _result(stored, published=published)


def _validate_batch(
    batch: ThreatBatch,
    *,
    expected_source: str,
    now: datetime,
) -> SourceVersion:
    if not isinstance(batch, ThreatBatch):
        raise ValidationError("Threat feed returned an invalid batch")
    if batch.source != expected_source:
        raise ValidationError("Threat feed source does not match the configured source")
    source_version = SourceVersion(batch.source, batch.source_version)
    if batch.generated_at > now:
        raise ValidationError("Threat feed generation time is in the future")
    if batch.valid_until <= now or batch.valid_until <= batch.generated_at:
        raise ValidationError("Threat feed batch is expired")
    return source_version


def _map_records(batch: ThreatBatch) -> tuple[ThreatRecord, ...]:
    records: list[ThreatRecord] = []
    try:
        for item in batch.records:
            if item.normalization_version != NORMALIZATION_VERSION:
                raise ValueError("record normalization version is not supported")
            records.append(
                ThreatRecord(
                    source=batch.source,
                    source_record_id=item.source_record_id,
                    indicator=ThreatIndicator.from_raw(
                        IndicatorType(item.indicator_type),
                        item.value,
                    ),
                    status=ThreatRecordStatus(item.status),
                    first_seen_at=item.first_seen_at,
                    observed_at=item.observed_at,
                    expires_at=item.expires_at,
                    evidence_ref=item.evidence_ref,
                    verification_source=item.verification_source,
                )
            )
    except (TypeError, ValueError) as exc:
        raise ValidationError("Threat feed contains an invalid record") from exc
    return tuple(records)


def _record_sort_key(record: ThreatRecord) -> tuple[str, str, str, str]:
    return (
        record.source,
        record.source_record_id,
        record.indicator.indicator_type.value,
        record.indicator.normalized_value,
    )


def _snapshot_digest(
    source_version: SourceVersion,
    valid_until: datetime,
    records: tuple[ThreatRecord, ...],
) -> str:
    value = {
        "source_versions": [{"source": source_version.source, "version": source_version.version}],
        "valid_until": _timestamp(valid_until),
        "records": [
            {
                "source": record.source,
                "source_record_id": record.source_record_id,
                "indicator_type": record.indicator.indicator_type.value,
                "normalized_value": record.indicator.normalized_value,
                "normalization_version": record.indicator.normalization_version,
                "status": record.status.value,
                "first_seen_at": _timestamp(record.first_seen_at),
                "observed_at": _timestamp(record.observed_at),
                "expires_at": _timestamp(record.expires_at),
                "evidence_ref": record.evidence_ref,
                "verification_source": record.verification_source,
            }
            for record in records
        ],
    }
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _source_version(snapshot: RegistrySnapshot, source: str) -> SourceVersion | None:
    return next((item for item in snapshot.source_versions if item.source == source), None)


def _result(snapshot: RegistrySnapshot, *, published: bool) -> RefreshRegistryResult:
    return RefreshRegistryResult(
        snapshot_id=snapshot.snapshot_id,
        snapshot_version=snapshot.version,
        source_versions=tuple(f"{item.source}@{item.version}" for item in snapshot.source_versions),
        record_count=snapshot.record_count,
        content_sha256=snapshot.content_sha256,
        published=published,
    )
