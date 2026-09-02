"""Common adapter behavior and compatibility reporting."""

from __future__ import annotations

from codecortex.backends.contracts import BackendCompatibilityError, BackendStatus
from codecortex.backends.manager import BackendManager
from codecortex.backends.spec import BackendSpec


class ManagedAdapterMixin:
    contract_version = 1
    manager: BackendManager
    spec: BackendSpec

    def status(self) -> BackendStatus:
        installed = self.manager.is_installed(self.spec)
        healthy = self.manager.probe(self.spec, provision=False) if installed else False
        return BackendStatus(
            key=self.spec.key,
            installed=installed,
            healthy=healthy,
            revision=self.spec.revision,
            contract_version=self.contract_version,
            capabilities=self.spec.capabilities,
        )

    @staticmethod
    def require_tools(catalog: list[dict[str, object]], required: set[str]) -> None:
        available = {str(item.get("name")) for item in catalog if isinstance(item.get("name"), str)}
        missing = sorted(required - available)
        if missing:
            raise BackendCompatibilityError(
                "backend tool contract mismatch; missing: " + ", ".join(missing)
            )
