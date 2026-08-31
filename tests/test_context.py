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
