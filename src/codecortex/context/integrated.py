"""Context processor that opportunistically uses the mature compression backend."""

from __future__ import annotations

import asyncio

from codecortex.backends.context import ContextBackendAdapter
from codecortex.backends.mcp_client import MCPStdioClient
from codecortex.context.budget import BudgetContextProcessor
from codecortex.core.contracts import ContextProcessor
from codecortex.core.models import ContextChunk


class IntegratedContextProcessor(ContextProcessor):
    def __init__(
        self,
        backend: ContextBackendAdapter | None = None,
        *,
        compression_threshold: int = 512,
    ) -> None:
        self.backend = backend
        self.compression_threshold = compression_threshold
        self.budget = BudgetContextProcessor()

    async def fit(self, chunks: list[ContextChunk], budget: int) -> list[ContextChunk]:
        backend = self.backend
        if backend is None or not await backend.health():
            return await self.budget.fit(chunks, budget)
        candidates = [chunk for chunk in chunks if chunk.tokens >= self.compression_threshold]
        if not candidates:
            return await self.budget.fit(chunks, budget)
        try:
            payloads = await asyncio.to_thread(
                backend.compress_batch,
                [chunk.content for chunk in candidates],
            )
        except Exception:
            return await self.budget.fit(chunks, budget)
        replacements: dict[int, ContextChunk] = {}
        for chunk, payload in zip(candidates, payloads, strict=True):
            content = MCPStdioClient.content_text(payload).strip()
            if not content:
                continue
            compressed_tokens = max(1, len(content) // 4)
            if compressed_tokens >= chunk.tokens:
                continue
            metadata = dict(chunk.metadata)
            metadata.update(
                {
                    "compressed": True,
                    "original_tokens": chunk.tokens,
                    "compression_backend": backend.spec.key,
                    "compression_revision": backend.spec.revision,
                }
            )
            replacements[id(chunk)] = chunk.model_copy(
                update={"content": content, "tokens": compressed_tokens, "metadata": metadata}
            )
        normalized = [replacements.get(id(chunk), chunk) for chunk in chunks]
        return await self.budget.fit(normalized, budget)
