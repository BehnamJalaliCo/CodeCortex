import pytest

from codecortex.evaluation import (
    EvaluationCase,
    EvaluationExpectation,
    EvaluationOutput,
    ExternalEvaluationSuite,
)


class FakeTarget:
    name = "fake"

    async def run(self, case: EvaluationCase) -> EvaluationOutput:
        return EvaluationOutput(
            answer="The authentication entry point is src/auth.py",
            files_touched=("src/auth.py",),
            tokens=100,
            tool_calls=2,
        )


@pytest.mark.asyncio
async def test_external_suite_grades_reproducible_expectations() -> None:
    suite = ExternalEvaluationSuite(
        "test-suite",
        [
            EvaluationCase(
                id="auth",
                prompt="Find auth",
                expectation=EvaluationExpectation(
                    required_strings=("authentication",),
                    required_paths=("src/auth.py",),
                    max_tokens=200,
                    max_tool_calls=5,
                ),
            )
        ],
    )
    report = await suite.run(FakeTarget())
    assert report.results[0].grade.passed is True
    assert report.summary()["success_rate"] == 1.0
