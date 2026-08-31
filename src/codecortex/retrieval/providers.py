"""Embedding provider contracts and local/optional implementations."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_.$:/-]*")


class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FeatureHashEmbeddingProvider:
    """Deterministic zero-network fallback suitable for local code retrieval."""

    name = "feature-hash-v1"

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions < 64:
            raise ValueError("dimensions must be >= 64")
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = [token.lower() for token in _TOKEN.findall(text)]
        features = tokens + [f"{a}::{b}" for a, b in zip(tokens, tokens[1:])]
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            raw = int.from_bytes(digest, "little")
            index = raw % self.dimensions
            sign = -1.0 if raw & 1 else 1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class SentenceTransformerEmbeddingProvider:
    """Optional local neural provider loaded only when the semantic extra is installed."""

    def __init__(self, model: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Install CodeCortex with the 'semantic' extra to use neural embeddings."
            ) from exc
        self._model = SentenceTransformer(model)
        self.name = f"sentence-transformer:{model}"
        probe = self._model.encode(["codecortex"], normalize_embeddings=True)
        self.dimensions = int(len(probe[0]))

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in row] for row in vectors]
