"""Token-budget aware context processing."""

from __future__ import annotations

from codecortex.core.contracts import ContextProcessor
from codecortex.core.models import ContextChunk


class BudgetContextProcessor(ContextProcessor):
    """Keep the highest-value chunks while respecting a hard token budget."""

    async def fit(self, chunks: list[ContextChunk], budget: int) -> list[ContextChunk]:
        ranked = sorted(
            chunks,
            key=lambda chunk: (chunk.relevance, -chunk.tokens),
            reverse=True,
        )
        selected: list[ContextChunk] = []
        used = 0
        for chunk in ranked:
            if chunk.tokens > budget:
                continue
            if used + chunk.tokens > budget:
                continue
            selected.append(chunk)
            used += chunk.tokens
        return selected
