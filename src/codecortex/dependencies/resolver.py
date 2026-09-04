"""Merge declared constraints with lockfile-resolved versions."""

from __future__ import annotations

from pathlib import Path

from codecortex.dependencies.manifests import ManifestScanner
from codecortex.dependencies.models import (
    DependencyInventory,
    DependencyRecord,
    DependencyScope,
)


class DependencyResolver:
    """Build a single inventory in which each dependency keeps both versions."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def inventory(self) -> DependencyInventory:
        records, manifests = ManifestScanner(self.root).scan()
        merged: dict[str, DependencyRecord] = {}
        for record in records:
            existing = merged.get(record.key)
            merged[record.key] = record if existing is None else self._merge(existing, record)
        ordered = sorted(
            merged.values(), key=lambda item: (item.ecosystem.value, item.name.lower())
        )
        return DependencyInventory(records=tuple(ordered), manifests=manifests)

    @staticmethod
    def _merge(existing: DependencyRecord, incoming: DependencyRecord) -> DependencyRecord:
        """Combine two views of the same dependency.

        A declared constraint from a manifest and a pinned version from a
        lockfile describe different things, so both are retained. The narrower
        scope wins so a package listed as both runtime and dev stays runtime.
        """
        scope_order = {
            DependencyScope.RUNTIME: 0,
            DependencyScope.BUILD: 1,
            DependencyScope.OPTIONAL: 2,
            DependencyScope.DEVELOPMENT: 3,
        }
        scope = min(
            (existing.scope, incoming.scope), key=lambda item: scope_order.get(item, 9)
        )
        declared_source = existing if existing.declared else incoming
        return DependencyRecord(
            ecosystem=existing.ecosystem,
            name=existing.name,
            declared=existing.declared or incoming.declared,
            resolved=existing.resolved or incoming.resolved,
            manifest=declared_source.manifest or existing.manifest,
            lock_source=existing.lock_source or incoming.lock_source,
            scope=scope,
        )
