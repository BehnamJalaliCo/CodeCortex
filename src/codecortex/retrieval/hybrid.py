"""Hybrid retrieval combining vector, lexical, and structural priors."""

from __future__ import annotations

import re
from dataclasses import dataclass

from codecortex.retrieval.index import SemanticDocument, SemanticIndex


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    document: SemanticDocument
    score: float
    vector_score: float
    lexical_score: float
    structural_score: float


class HybridRetriever:
    def __init__(
        self,
        index: SemanticIndex,
        vector_weight: float = 0.60,
        lexical_weight: float = 0.30,
        structural_weight: float = 0.10,
    ) -> None:
        total = vector_weight + lexical_weight + structural_weight
        if total <= 0:
            raise ValueError("retrieval weights must sum to a positive value")
        self.index = index
        self.vector_weight = vector_weight / total
        self.lexical_weight = lexical_weight / total
        self.structural_weight = structural_weight / total

    def search(self, query: str, limit: int = 20) -> list[RetrievalHit]:
        candidates = self.index.search(query, limit=max(limit * 4, 40))
        query_terms = {term.lower() for term in re.findall(r"[A-Za-z_][\w.-]*", query)}
        hits: list[RetrievalHit] = []
        for match in candidates:
            text_terms = {term.lower() for term in re.findall(r"[A-Za-z_][\w.-]*", match.document.text)}
            lexical = len(query_terms & text_terms) / max(1, len(query_terms))
            metadata = match.document.metadata
            structural = 0.0
            path = str(metadata.get("path", "")).lower()
            symbol = str(metadata.get("symbol", "")).lower()
            if any(term in path for term in query_terms):
                structural += 0.45
            if any(term == symbol for term in query_terms):
                structural += 0.55
            vector_score = (match.score + 1.0) / 2.0
            score = (
                self.vector_weight * vector_score
                + self.lexical_weight * lexical
                + self.structural_weight * min(1.0, structural)
            )
            hits.append(
                RetrievalHit(
                    document=match.document,
                    score=score,
                    vector_score=vector_score,
                    lexical_score=lexical,
                    structural_score=min(1.0, structural),
                )
            )
        hits.sort(key=lambda item: (-item.score, item.document.id))
        return hits[:limit]
