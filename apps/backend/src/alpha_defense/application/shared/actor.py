"""Server-created actor context passed into application commands."""

from dataclasses import dataclass
from enum import StrEnum

from alpha_defense.domain.shared import EntityId, ExecutionMode


class ActorRole(StrEnum):
    """Roles available in the mock-only MVP."""

    DEMO_USER = "demo_user"
    RESEARCHER = "researcher"


@dataclass(frozen=True, slots=True)
class ActorContext:
    """Trusted identity, namespace, consent revision, and execution mode."""

    user_id: EntityId
    session_id: EntityId
    namespace_id: EntityId
    roles: frozenset[ActorRole]
    consent_revision: int
    execution_mode: ExecutionMode

    def __post_init__(self) -> None:
        for field_name in ("user_id", "session_id", "namespace_id"):
            if not isinstance(getattr(self, field_name), EntityId):
                raise TypeError(f"{field_name} must be an EntityId")
        if not isinstance(self.roles, frozenset):
            raise TypeError("roles must be a frozenset")
        if not self.roles or any(not isinstance(role, ActorRole) for role in self.roles):
            raise ValueError("roles must contain at least one ActorRole")
        if type(self.consent_revision) is not int:
            raise TypeError("consent_revision must be an integer and must not be bool")
        if self.consent_revision < 0:
            raise ValueError("consent_revision must not be negative")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("execution_mode must be an ExecutionMode")

    def has_role(self, role: ActorRole) -> bool:
        """Return whether the server assigned the requested role."""

        return role in self.roles
