"""Allowlisted synthetic profiles; request payload cannot select a role."""

from alpha_defense.application.identity import AuthenticatedDemoSubject
from alpha_defense.domain.identity import SessionRole


class SyntheticIdentityProvider:
    _PROFILES = frozenset({"demo-user", "demo-senior"})

    def authenticate(self, profile_code: str) -> AuthenticatedDemoSubject | None:
        if profile_code not in self._PROFILES:
            return None
        return AuthenticatedDemoSubject(
            profile_code=profile_code,
            roles=frozenset({SessionRole.DEMO_USER}),
        )
