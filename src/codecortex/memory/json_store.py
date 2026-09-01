"""Process-safe local JSON memory backend."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from codecortex.core.contracts import MemoryStore
from codecortex.state import AtomicJsonFile


class JsonMemoryStore(MemoryStore):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, namespace: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", namespace).strip("._") or "namespace"
        digest = hashlib.blake2b(namespace.encode("utf-8"), digest_size=6).hexdigest()
        return self.root / f"{safe}-{digest}.json"

    def _store(self, namespace: str) -> AtomicJsonFile:
        return AtomicJsonFile(self._path(namespace))

    def _load(self, namespace: str) -> dict[str, str]:
        data = self._store(namespace).read({})
        if not isinstance(data, dict):
            return {}
        return {str(key): str(value) for key, value in data.items()}

    async def put(self, namespace: str, key: str, value: str) -> None:
        if not namespace.strip() or not key.strip():
            raise ValueError("namespace and key are required")

        def update(current: object) -> dict[str, str]:
            data = (
                {str(k): str(v) for k, v in current.items()}
                if isinstance(current, dict)
                else {}
            )
            data[key] = value
            return data

        self._store(namespace).update(update, default={})

    async def get(self, namespace: str, key: str) -> str | None:
        return self._load(namespace).get(key)

    async def search(self, namespace: str, query: str, limit: int = 10) -> list[str]:
        terms = {term.lower() for term in query.split() if term.strip()}
        data = self._load(namespace)
        scored: list[tuple[int, str]] = []
        for key, value in data.items():
            haystack = f"{key} {value}".lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                scored.append((score, value))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [value for _, value in scored[: max(1, limit)]]
