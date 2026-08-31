import pytest

from codecortex.context.integrated import IntegratedContextProcessor
from codecortex.core.models import ContextChunk


@pytest.mark.asyncio
async def test_integrated_context_falls_back_without_backend() -> None:
    processor = IntegratedContextProcessor(None)
    chunks = [ContextChunk(source="x", content="a" * 800, tokens=200, relevance=1.0)]
    result = await processor.fit(chunks, 100)
    assert len(result) == 1
    assert result[0].tokens == 100
    assert result[0].metadata["truncated"] is True
