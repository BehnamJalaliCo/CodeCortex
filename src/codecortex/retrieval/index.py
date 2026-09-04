"""Persistent semantic vector index."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from codecortex.retrieval.providers import EmbeddingProvider
from codecortex.state import AtomicJsonFile


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

    @property
    def document_ids(self) -> set[str]:
        return set(self._documents)

    def document(self, document_id: str) -> SemanticDocument | None:
        return self._documents.get(document_id)

    def upsert(self, documents: list[SemanticDocument]) -> None:
        if not documents:
            return
        vectors = self.provider.embed([document.text for document in documents])
        for document, vector in zip(documents, vectors, strict=True):
            self._documents[document.id] = document
            self._vectors[document.id] = vector
        if self.path:
            self.save()

    def replace(self, documents: list[SemanticDocument]) -> None:
        self._documents.clear()
        self._vectors.clear()
        self.upsert(documents)
        if not documents and self.path:
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
            for score, document_id in ranked[: max(1, limit)]
        ]

    def save(self) -> None:
        if self.path is None:
            return
        AtomicJsonFile(self.path).write(
            {
                "version": self.VERSION,
                "provider": self.provider.name,
                "dimensions": self.provider.dimensions,
                "documents": {
                    document_id: asdict(document)
                    for document_id, document in sorted(self._documents.items())
                },
                "vectors": self._vectors,
            }
        )

    def load(self) -> None:
        if self.path is None:
            return
        payload = AtomicJsonFile(self.path).read({})
        if (
            not isinstance(payload, dict)
            or payload.get("version") != self.VERSION
            or payload.get("provider") != self.provider.name
            or int(payload.get("dimensions", -1)) != self.provider.dimensions
        ):
            return
        documents = payload.get("documents", {})
        vectors = payload.get("vectors", {})
        if not isinstance(documents, dict) or not isinstance(vectors, dict):
            return
        self._documents = {
            str(document_id): SemanticDocument(
                id=str(value["id"]),
                text=str(value["text"]),
                metadata=dict(value.get("metadata", {})),
            )
            for document_id, value in documents.items()
            if isinstance(value, dict) and "id" in value and "text" in value
        }
        self._vectors = {
            str(document_id): [float(value) for value in vector]
            for document_id, vector in vectors.items()
            if document_id in self._documents and isinstance(vector, list)
        }

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            return -1.0
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left)) or 1.0
        right_norm = math.sqrt(sum(value * value for value in right)) or 1.0
        return dot / (left_norm * right_norm)
