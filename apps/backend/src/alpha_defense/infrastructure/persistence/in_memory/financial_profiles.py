"""Copy-on-write profile history with an append-only update contract."""

from __future__ import annotations

from alpha_defense.application.shared import StaleRevisionError
from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.transfers import FinancialProfile
from alpha_defense.infrastructure.persistence.in_memory.store import InMemoryState


class InMemoryProfileRepository:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state

    def get(self, profile_id: EntityId) -> FinancialProfile | None:
        return self._state.financial_profiles.get(profile_id)

    def get_by_template(
        self, *, owner_id: EntityId, namespace_id: EntityId, template_code: str
    ) -> FinancialProfile | None:
        profile_id = self._state.profile_templates.get((owner_id, namespace_id, template_code))
        return None if profile_id is None else self.get(profile_id)

    def list_owned(
        self, *, owner_id: EntityId, namespace_id: EntityId
    ) -> tuple[FinancialProfile, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self._state.financial_profiles.values()
                    if item.owner_id == owner_id and item.namespace_id == namespace_id
                ),
                key=lambda item: (item.created_at, str(item.profile_id)),
            )
        )

    def add(self, profile: FinancialProfile) -> None:
        key = (profile.owner_id, profile.namespace_id, profile.template_code)
        if (
            profile.profile_id in self._state.financial_profiles
            or key in self._state.profile_templates
        ):
            raise ValueError("profile or template already exists")
        used_ids = {
            operation.operation_id
            for existing in self._state.financial_profiles.values()
            for operation in existing.operations
        }
        if any(item.operation_id in used_ids for item in profile.operations):
            raise ValueError("completed operation already exists")
        self._state.financial_profiles[profile.profile_id] = profile
        self._state.profile_templates[key] = profile.profile_id

    def append_completed(self, profile: FinancialProfile, *, expected_version: int) -> None:
        current = self.get(profile.profile_id)
        if current is None or current.history_version != expected_version:
            raise StaleRevisionError("Profile version is stale")
        current.assert_successor(profile)
        if any(
            profile.operations[-1].operation_id == item.operation_id
            for existing in self._state.financial_profiles.values()
            for item in existing.operations
        ):
            raise ValueError("completed operation already exists")
        self._state.financial_profiles[profile.profile_id] = profile
