"""Simple local JSON memory backend."""

from __future__ import annotations

import json
import re
from pathlib import Path

from codecortex.core.contracts import MemoryStore


class JsonMemoryStore(MemoryStore):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, namespace: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", namespace)
        return self.root / f"{safe}.json"

    def _load(self, namespace: str) -> dict[str, str]:
        path = self._path(namespace)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {str(key): str(value) for key, value in data.items()}

    async def put(self, namespace: str, key: str, value: str) -> None:
        data = self._load(namespace)
        data[key] = value
        path = self._path(namespace)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)

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
        return [value for _, value in scored[:limit]]
