"""Authentication primitives for the embedded and hosted HTTP service."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ApiSecuritySettings:
    require_auth: bool = False
    tokens: dict[str, str] = field(default_factory=dict)


class ApiTokenAuthenticator:
    """Authenticate bearer tokens without retaining plaintext digests for comparison."""

    def __init__(self, settings: ApiSecuritySettings | None = None) -> None:
        self.settings = settings or ApiSecuritySettings()
        self._digests = {
            hashlib.sha256(token.encode("utf-8")).digest(): principal
            for principal, token in self.settings.tokens.items()
            if principal.strip() and token
        }

    def authenticate(self, authorization: str | None) -> str | None:
        if not self._digests:
            return None if self.settings.require_auth else "local-admin"
        if not authorization or not authorization.startswith("Bearer "):
            return None
        candidate = hashlib.sha256(authorization[7:].encode("utf-8")).digest()
        for digest, principal in self._digests.items():
            if hmac.compare_digest(candidate, digest):
                return principal
        return None

    @property
    def configured(self) -> bool:
        return bool(self._digests)
