"""Stable CodeCortex-side contracts for optional mature backends.

These interfaces are the compatibility boundary. CodeCortex code outside this
package must not import backend implementation modules or internal APIs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from codecortex.backends.spec import BackendSpec


@dataclass(frozen=True, slots=True)
class BackendStatus:
    key: str
    installed: bool
    healthy: bool
    revision: str
    contract_version: int
    capabilities: tuple[str, ...]
    detail: str = ""


class BackendCompatibilityError(RuntimeError):
    pass


@runtime_checkable
class ManagedBackend(Protocol):
    spec: BackendSpec
    contract_version: int

    async def health(self) -> bool: ...

    def status(self) -> BackendStatus: ...


@runtime_checkable
class GraphIntelligence(ManagedBackend, Protocol):
    def build(self) -> dict[str, Any]: ...

    def query(self, query: str) -> str: ...

    def explain(self, node: str) -> str: ...

    def path(self, source: str, target: str) -> str: ...


@runtime_checkable
class SymbolIntelligence(ManagedBackend, Protocol):
    def tools(self) -> list[dict[str, Any]]: ...

    def call(self, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class ContextIntelligence(ManagedBackend, Protocol):
    def compress(self, content: str) -> dict[str, Any]: ...

    def retrieve(self, hash_key: str) -> dict[str, Any]: ...

    def stats(self) -> dict[str, Any]: ...
