"""TTL cache for dependency documentation results."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

from codecortex.dependencies.models import DocumentationEvidence
from codecortex.state import AtomicJsonFile

#: Bumped whenever the cached payload shape changes.
CACHE_VERSION = 1


@dataclass(frozen=True, slots=True)
class CacheLookup:
    """A cache probe result that always states whether the entry was fresh."""

    evidence: tuple[DocumentationEvidence, ...] | None
    stale: bool
    age_seconds: float = 0.0

    @property
    def hit(self) -> bool:
        return self.evidence is not None


class DocumentationCache:
    """Persist documentation results so repeat questions stay local and cheap."""

    def __init__(self, path: Path, ttl_seconds: int = 86_400, max_entries: int = 256) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.state = AtomicJsonFile(path)

    @staticmethod
    def key(provider: str, library_id: str, version: str | None, query: str) -> str:
        payload = "\n".join(
            [
                str(CACHE_VERSION),
                provider,
                library_id.lower(),
                (version or "unpinned").lower(),
                " ".join(query.lower().split()),
            ]
        )
        return hashlib.blake2b(payload.encode("utf-8"), digest_size=20).hexdigest()

    def _entries(self) -> dict[str, dict[str, object]]:
        payload = self.state.read({})
        if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
            return {}
        entries = payload.get("entries")
        return dict(entries) if isinstance(entries, dict) else {}

    def get(self, key: str, *, allow_stale: bool = False) -> CacheLookup:
        """Return a cached result, marking it stale when the TTL has expired."""
        entry = self._entries().get(key)
        if not isinstance(entry, dict):
            return CacheLookup(None, False)
        raw_created = entry.get("created", 0.0)
        created = float(raw_created) if isinstance(raw_created, (int, float)) else 0.0
        age = max(0.0, time.time() - created)
        stale = age > self.ttl_seconds
        if stale and not allow_stale:
            return CacheLookup(None, True, age)
        raw = entry.get("evidence")
        if not isinstance(raw, list):
            return CacheLookup(None, stale, age)
        evidence = tuple(
            DocumentationEvidence(
                library_id=str(item.get("library_id", "")),
                content=str(item.get("content", "")),
                version=item.get("version"),
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                provider=str(item.get("provider", "")),
                stale=stale,
                metadata=dict(item.get("metadata", {})),
            )
            for item in raw
            if isinstance(item, dict)
        )
        return CacheLookup(evidence, stale, age)

    def put(self, key: str, evidence: list[DocumentationEvidence]) -> None:
        def update(payload: object) -> dict[str, object]:
            current = (
                payload
                if isinstance(payload, dict) and payload.get("version") == CACHE_VERSION
                else {"version": CACHE_VERSION, "entries": {}}
            )
            raw = current.get("entries")
            entries = dict(raw) if isinstance(raw, dict) else {}
            entries[key] = {
                "created": time.time(),
                "evidence": [item.to_dict() for item in evidence],
            }
            ordered = sorted(
                entries.items(),
                key=lambda pair: float(pair[1].get("created", 0.0))
                if isinstance(pair[1], dict)
                else 0.0,
                reverse=True,
            )[: self.max_entries]
            return {"version": CACHE_VERSION, "entries": dict(ordered)}

        self.state.update(update, default={})

    def writable(self) -> bool:
        """Return True when the cache directory can be created and written."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            probe = self.path.parent / ".write-probe"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
        except OSError:
            return False
        return True
