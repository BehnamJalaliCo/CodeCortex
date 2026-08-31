from codecortex.core.models import AgentRequest, Capability, RequestKind
from codecortex.router import AdaptiveRouter


def test_router_selects_symbols_for_code_change() -> None:
    router = AdaptiveRouter()
    plan = router.route(AgentRequest(query="Fix the authentication race in refresh_token"))

    assert plan.request_kind in {RequestKind.DEBUG, RequestKind.CHANGE}
    assert Capability.SYMBOLS in plan.selected
    assert Capability.VALIDATION in plan.selected


def test_router_uses_memory_for_previous_decisions() -> None:
    router = AdaptiveRouter()
    plan = router.route(AgentRequest(query="Remember the previous architecture decision"))

    assert Capability.MEMORY in plan.selected


def test_route_scores_are_bounded() -> None:
    router = AdaptiveRouter()
    plan = router.route(AgentRequest(query="Explain the architecture and context"))

    assert all(0.0 <= item.score <= 1.0 for item in plan.scores)
