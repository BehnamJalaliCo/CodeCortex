"""Token-budget aware context processing."""

from __future__ import annotations

from codecortex.core.contracts import ContextProcessor
from codecortex.core.models import ContextChunk


class BudgetContextProcessor(ContextProcessor):
    """Deduplicate, rank, and fit useful context inside a token budget."""

    async def fit(self, chunks: list[ContextChunk], budget: int) -> list[ContextChunk]:
        unique = self._deduplicate(chunks)
        ranked = sorted(
            unique,
            key=lambda chunk: (chunk.relevance, -chunk.tokens),
            reverse=True,
        )

        selected: list[ContextChunk] = []
        remaining = budget
        for chunk in ranked:
            if remaining <= 0:
                break
            if chunk.tokens <= remaining:
                selected.append(chunk)
                remaining -= chunk.tokens
                continue
            if remaining < 32:
                continue
            selected.append(self._truncate(chunk, remaining))
            remaining = 0
        return selected

    @staticmethod
    def _deduplicate(chunks: list[ContextChunk]) -> list[ContextChunk]:
        by_content: dict[str, ContextChunk] = {}
        for chunk in chunks:
            key = " ".join(chunk.content.split())
            current = by_content.get(key)
            if current is None or chunk.relevance > current.relevance:
                by_content[key] = chunk
        return list(by_content.values())

    @staticmethod
    def _truncate(chunk: ContextChunk, tokens: int) -> ContextChunk:
        char_limit = max(1, tokens * 4)
        content = chunk.content[:char_limit].rstrip()
        metadata = dict(chunk.metadata)
        metadata.update(
            {
                "truncated": True,
                "original_tokens": chunk.tokens,
            }
        )
        return chunk.model_copy(
            update={
                "content": content,
                "tokens": tokens,
                "metadata": metadata,
            }
        )
