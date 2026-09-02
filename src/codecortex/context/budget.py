"""Token-budget aware context processing."""

from __future__ import annotations

from codecortex.context.tokenizer import AutoTokenCounter, TokenCounter
from codecortex.core.contracts import ContextProcessor
from codecortex.core.models import ContextChunk


class BudgetContextProcessor(ContextProcessor):
    """Deduplicate, rank, and fit useful context inside a token budget."""

    def __init__(self, token_counter: TokenCounter | None = None) -> None:
        self.token_counter = token_counter or AutoTokenCounter()

    async def fit(self, chunks: list[ContextChunk], budget: int) -> list[ContextChunk]:
        if budget < 1:
            raise ValueError("budget must be positive")
        normalized = [
            chunk.model_copy(update={"tokens": self.token_counter.count(chunk.content)})
            for chunk in chunks
        ]
        unique = self._deduplicate(normalized)
        ranked = sorted(unique, key=lambda chunk: (chunk.relevance, -chunk.tokens), reverse=True)
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
            truncated = self._truncate(chunk, remaining)
            if truncated.content:
                selected.append(truncated)
                remaining -= truncated.tokens
        return selected

    @staticmethod
    def _deduplicate(chunks: list[ContextChunk]) -> list[ContextChunk]:
        by_content_and_provenance: dict[tuple[str, str], ContextChunk] = {}
        for chunk in chunks:
            normalized = " ".join(chunk.content.split())
            provenance = str(chunk.metadata.get("path") or chunk.source)
            key = (normalized, provenance)
            current = by_content_and_provenance.get(key)
            if current is None or chunk.relevance > current.relevance:
                by_content_and_provenance[key] = chunk
        return list(by_content_and_provenance.values())

    def _truncate(self, chunk: ContextChunk, tokens: int) -> ContextChunk:
        content = self.token_counter.truncate(chunk.content, tokens)
        actual_tokens = self.token_counter.count(content)
        metadata = dict(chunk.metadata)
        metadata.update({"truncated": True, "original_tokens": chunk.tokens})
        return chunk.model_copy(
            update={"content": content, "tokens": actual_tokens, "metadata": metadata}
        )
