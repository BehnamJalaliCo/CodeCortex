import pytest

from codecortex.context.pipeline import ContextPipeline
from codecortex.core.models import ContextChunk


@pytest.mark.asyncio
async def test_context_pipeline_ranks_and_caches(tmp_path):
    pipeline = ContextPipeline(tmp_path)
    chunks = [
        ContextChunk(source="a", content="authentication token refresh", tokens=20, relevance=0.6),
        ContextChunk(source="b", content="image rendering pipeline", tokens=20, relevance=0.8),
        ContextChunk(source="c", content="authentication token refresh", tokens=20, relevance=0.5),
    ]
    first = await pipeline.prepare("fix authentication token", chunks, budget=25)
    assert first.chunks[0].source == "a"
    assert first.metrics.tokens_saved > 0
    second = await pipeline.prepare("fix authentication token", chunks, budget=25)
    assert second.metrics.cache_hit is True
