from pathlib import Path
from codecortex.platform_dod import DefinitionOfDone, FeatureCompletion


def test_definition_of_done_rejects_incomplete_feature() -> None:
    dod = DefinitionOfDone.load(Path("platform/definition_of_done.json"))
    completion = FeatureCompletion("example", {item: True for item in dod.required})
    assert dod.done(completion)
    completion.checks["unit_tests"] = False
    assert not dod.done(completion)
    assert dod.validate(completion) == ("unit_tests",)


def test_definition_of_done_includes_security_and_regression_decisions() -> None:
    dod = DefinitionOfDone.load(Path("platform/definition_of_done.json"))
    assert "authorization_defined" in dod.required
    assert "audit_requirement_defined" in dod.required
    assert "no_regression" in dod.required
