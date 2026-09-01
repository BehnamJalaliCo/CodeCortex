import pytest

from codecortex.context import BudgetContextProcessor
from codecortex.core.models import ContextChunk


@pytest.mark.asyncio
async def test_context_processor_respects_budget() -> None:
    processor = BudgetContextProcessor()
    chunks = [
        ContextChunk(source="a", content="high", tokens=60, relevance=0.9),
        ContextChunk(source="b", content="medium", tokens=50, relevance=0.7),
        ContextChunk(source="c", content="low", tokens=40, relevance=0.2),
    ]

    result = await processor.fit(chunks, budget=100)

    assert sum(chunk.tokens for chunk in result) <= 100
    assert result[0].source == "a"


@pytest.mark.asyncio
async def test_context_processor_preserves_distinct_provenance() -> None:
    processor = BudgetContextProcessor()
    chunks = [
        ContextChunk(source="a", content="same content", tokens=20, relevance=0.5),
        ContextChunk(source="b", content="same   content", tokens=20, relevance=0.9),
    ]

    result = await processor.fit(chunks, budget=100)

    assert len(result) == 2
    assert result[0].source == "b"
    assert {chunk.source for chunk in result} == {"a", "b"}


@pytest.mark.asyncio
async def test_context_processor_truncates_large_chunk() -> None:
    processor = BudgetContextProcessor()
    chunk = ContextChunk(source="large", content="x" * 800, tokens=200, relevance=1.0)

    result = await processor.fit([chunk], budget=100)

    assert len(result) == 1
    assert result[0].tokens == 100
    assert result[0].metadata["truncated"] is True
