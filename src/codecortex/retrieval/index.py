"""Persistent semantic vector index."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from codecortex.retrieval.providers import EmbeddingProvider


@dataclass(frozen=True, slots=True)
class SemanticDocument:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SemanticMatch:
    document: SemanticDocument
    score: float


class SemanticIndex:
    VERSION = 1

    def __init__(self, provider: EmbeddingProvider, path: Path | None = None) -> None:
        self.provider = provider
        self.path = path
        self._documents: dict[str, SemanticDocument] = {}
        self._vectors: dict[str, list[float]] = {}
        if path and path.exists():
            self.load()

    def upsert(self, documents: list[SemanticDocument]) -> None:
        if not documents:
            return
        vectors = self.provider.embed([document.text for document in documents])
        for document, vector in zip(documents, vectors, strict=True):
            self._documents[document.id] = document
            self._vectors[document.id] = vector
        if self.path:
            self.save()

    def delete(self, ids: set[str]) -> None:
        for document_id in ids:
            self._documents.pop(document_id, None)
            self._vectors.pop(document_id, None)
        if self.path:
            self.save()

    def search(self, query: str, limit: int = 20, min_score: float = -1.0) -> list[SemanticMatch]:
        if not self._documents:
            return []
        query_vector = self.provider.embed([query])[0]
        ranked: list[tuple[float, str]] = []
        for document_id, vector in self._vectors.items():
            score = self._cosine(query_vector, vector)
            if score >= min_score:
                ranked.append((score, document_id))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [
            SemanticMatch(document=self._documents[document_id], score=score)
            for score, document_id in ranked[:limit]
        ]

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.VERSION,
            "provider": self.provider.name,
            "dimensions": self.provider.dimensions,
            "documents": {
                document_id: asdict(document)
                for document_id, document in sorted(self._documents.items())
            },
            "vectors": self._vectors,
        }
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.path)

    def load(self) -> None:
        if self.path is None:
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if payload.get("version") != self.VERSION:
            return
        if payload.get("provider") != self.provider.name:
            return
        if int(payload.get("dimensions", -1)) != self.provider.dimensions:
            return
        documents = payload.get("documents", {})
        vectors = payload.get("vectors", {})
        self._documents = {
            document_id: SemanticDocument(
                id=str(value["id"]),
                text=str(value["text"]),
                metadata=dict(value.get("metadata", {})),
            )
            for document_id, value in documents.items()
        }
        self._vectors = {
            document_id: [float(value) for value in vector]
            for document_id, vector in vectors.items()
            if document_id in self._documents
        }

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            return -1.0
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left)) or 1.0
        right_norm = math.sqrt(sum(value * value for value in right)) or 1.0
        return dot / (left_norm * right_norm)
