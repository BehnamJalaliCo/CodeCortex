"""MCP, CLI, and end-to-end coverage for the evidence-fusion surfaces."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codecortex.entrypoint import app
from codecortex.mcp.extended import ExtendedMCPApplication
from codecortex.mcp.server import MCPApplication, MCPServer
from codecortex.runtime import build_runtime
from tests.fixtures.precision_index import (
    DEFINITION,
    Document,
    IndexBuilder,
    Occurrence,
    SymbolInfo,
    symbol,
)

runner = CliRunner()

FAKE_ENGINE = Path(__file__).parent / "fixtures" / "structural_engine.py"
MIDDLEWARE = symbol("app", "middleware/`authenticate`().")
HANDLER = symbol("app", "routes/`handler`().")

MIDDLEWARE_SOURCE = """from framework import old_api


def authenticate(request):
    return old_api(request)
"""

ROUTES_SOURCE = """from middleware import authenticate


def handler(request):
    return authenticate(request)


def secondary(request):
    return old_api(request)
"""


def _project(tmp_path: Path) -> Path:
    """A small repository with a dependency manifest, a lockfile, and Git history."""
    root = tmp_path / "workspace"
    (root / "src").mkdir(parents=True)
    (root / "src" / "middleware.py").write_text(MIDDLEWARE_SOURCE, encoding="utf-8")
    (root / "src" / "routes.py").write_text(ROUTES_SOURCE, encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_routes.py").write_text(
        "from routes import handler\n\n\ndef test_handler():\n    assert handler(None) is not None\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "workspace"\ndependencies = ["framework>=2,<3"]\n', encoding="utf-8"
    )
    (root / "uv.lock").write_text(
        '[[package]]\nname = "framework"\nversion = "2.4.1"\n', encoding="utf-8"
    )
    (root / ".codecortex").mkdir()
    (root / ".codecortex" / "config.json").write_text(
        json.dumps(
            {
                "structural": {
                    "command": sys.executable,
                    "command_args": [str(FAKE_ENGINE)],
                }
            }
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "CodeCortex CI"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
    return root


def _write_precision_index(root: Path) -> Path:
    """Index the fixture with exact positions matching the sources above."""
    payload = (
        IndexBuilder()
        .add(
            Document(
                relative_path="src/middleware.py",
                occurrences=(Occurrence(MIDDLEWARE, 3, 4, 16, roles=DEFINITION),),
                symbols=(
                    SymbolInfo(
                        MIDDLEWARE,
                        display_name="authenticate",
                        documentation=("Authenticate a request.",),
                    ),
                ),
            )
        )
        .add(
            Document(
                relative_path="src/routes.py",
                occurrences=(
                    Occurrence(HANDLER, 3, 4, 11, roles=DEFINITION),
                    Occurrence(MIDDLEWARE, 4, 11, 23),
                ),
                symbols=(SymbolInfo(HANDLER, display_name="handler"),),
            )
        )
        .encode()
    )
    target = root / ".codecortex" / "precision" / "index.cortexidx"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    # Age the sources rather than post-dating the index, so the index is fresh
    # now and any later edit genuinely makes it stale.
    past = time.time() - 3_600
    for source in root.rglob("*.py"):
        os.utime(source, (past, past))
    return target


def _application(root: Path) -> MCPApplication:
    return MCPApplication(build_runtime(root))


def _ok(args: list[str]) -> str:
    result = runner.invoke(app, args)
    assert result.exit_code == 0, f"{args}: {result.stdout}\n{result.exception!r}"
    return result.stdout


# -- MCP surface ------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_mcp_tools_are_advertised_with_strict_schemas(tmp_path: Path) -> None:
    application = _application(_project(tmp_path))
    tools = {tool["name"]: tool for tool in application.tools()}
    expected = {
        "cortex_precise_definition",
        "cortex_precise_references",
        "cortex_precise_implementations",
        "cortex_symbol_occurrences",
        "cortex_precision_status",
        "cortex_dependency_info",
        "cortex_dependency_docs",
        "cortex_dependency_context",
        "cortex_structural_search",
        "cortex_rewrite_preview",
    }
    assert expected <= set(tools)
    for name in expected:
        schema = tools[name]["inputSchema"]
        assert schema["additionalProperties"] is False
        assert schema["type"] == "object"

    # Existing tools must keep working unchanged.
    assert {"cortex_repository_map", "cortex_context", "cortex_stats"} <= set(tools)


@pytest.mark.asyncio
async def test_precision_mcp_tools_return_exact_evidence(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _write_precision_index(root)
    application = _application(root)

    status = await application.call("cortex_precision_status", {})
    assert status["status"] == "available"
    assert status["documents"] == 2

    definition = await application.call(
        "cortex_precise_definition", {"path": "src/routes.py", "line": 5, "column": 12}
    )
    assert [item["path"] for item in definition["evidence"]] == ["src/middleware.py"]
    assert definition["evidence"][0]["exact"] is True
    assert definition["evidence"][0]["trust"] == "exact"
    assert definition["evidence"][0]["rank_score"] == 1.0
    assert definition["symbol"]["qualified_name"] == "middleware.authenticate"
    assert definition["degraded"] is False

    references = await application.call(
        "cortex_precise_references", {"path": "src/middleware.py", "line": 4, "column": 5}
    )
    assert [item["path"] for item in references["evidence"]] == ["src/routes.py"]
    assert references["exact_results"] == 1

    implementations = await application.call(
        "cortex_precise_implementations",
        {"path": "src/middleware.py", "line": 4, "column": 5},
    )
    assert implementations["evidence"] == []

    occurrences = await application.call("cortex_symbol_occurrences", {"symbol": MIDDLEWARE})
    assert occurrences["symbol"] == MIDDLEWARE
    assert [item["path"] for item in occurrences["evidence"]] == ["src/routes.py"]


@pytest.mark.asyncio
async def test_precision_mcp_tools_degrade_without_an_index(tmp_path: Path) -> None:
    application = _application(_project(tmp_path))
    status = await application.call("cortex_precision_status", {})
    assert status["status"] == "unavailable"

    definition = await application.call(
        "cortex_precise_definition", {"path": "src/routes.py", "line": 5, "column": 12}
    )
    assert definition["evidence"] == []
    assert definition["degraded"] is True
    provider = definition["providers"][0]
    assert provider["state"] == "unavailable"
    assert provider["fallback"] == "structural and heuristic graph resolution"


@pytest.mark.asyncio
async def test_dependency_mcp_tools_report_versions_without_network(tmp_path: Path) -> None:
    application = _application(_project(tmp_path))

    info = await application.call("cortex_dependency_info", {"library": "framework"})
    record = info["dependencies"][0]
    assert record["declared_version"] == ">=2,<3"
    assert record["resolved_version"] == "2.4.1"
    assert record["effective_version"] == "2.4.1"
    assert info["provider"]["status"] == "disabled"

    everything = await application.call("cortex_dependency_info", {})
    assert everything["library"] is None
    assert len(everything["dependencies"]) >= 1

    docs = await application.call(
        "cortex_dependency_docs", {"library": "framework", "query": "middleware"}
    )
    assert docs["documentation_available"] is False
    assert docs["resolved_version"] == "2.4.1"
    assert docs["provider"]["state"] == "not_configured"

    context = await application.call(
        "cortex_dependency_context", {"library": "framework", "query": "middleware"}
    )
    assert context["ecosystems"] == ["python"]
    assert "uv.lock" in {item["path"] for item in context["manifests"]}


@pytest.mark.asyncio
async def test_structural_mcp_search_and_preview(tmp_path: Path) -> None:
    root = _project(tmp_path)
    application = _application(root)

    found = await application.call(
        "cortex_structural_search", {"pattern": "old_api", "language": "python"}
    )
    assert {item["path"] for item in found["matches"]} == {
        "src/middleware.py",
        "src/routes.py",
    }
    assert found["engine"]["status"] == "available"

    scoped = await application.call(
        "cortex_structural_search",
        {"pattern": "old_api", "language": "python", "exclude": ["src/routes.py"]},
    )
    assert {item["path"] for item in scoped["matches"]} == {"src/middleware.py"}

    previewed = await application.call(
        "cortex_rewrite_preview",
        {"pattern": "old_api", "replacement": "new_api", "language": "python"},
    )
    preview = previewed["preview"]
    assert preview["total_matches"] == 3
    assert previewed["apply_with"] == "cortex_rewrite_apply"
    assert "old_api" in (root / "src" / "middleware.py").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_rewrite_apply_lives_only_on_the_mutating_surface(tmp_path: Path) -> None:
    root = _project(tmp_path)
    read_only = _application(root)
    assert "cortex_rewrite_apply" not in {tool["name"] for tool in read_only.tools()}
    with pytest.raises(KeyError, match="Unknown tool"):
        await read_only.call("cortex_rewrite_apply", {"preview_id": "x"})

    mutating = ExtendedMCPApplication(build_runtime(root))
    assert "cortex_rewrite_apply" in {tool["name"] for tool in mutating.tools()}
    preview = await mutating.call(
        "cortex_rewrite_preview",
        {"pattern": "old_api", "replacement": "new_api", "language": "python"},
    )
    applied = await mutating.call(
        "cortex_rewrite_apply", {"preview_id": preview["preview"]["preview_id"]}
    )
    assert applied["applied"] is True
    assert applied["files_changed"] == 2
    assert applied["matches_applied"] == 3
    assert applied["validation"]["passed"] is True
    assert "new_api" in (root / "src" / "middleware.py").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_mcp_rejects_bad_arguments_for_the_new_tools(tmp_path: Path) -> None:
    server = MCPServer(ExtendedMCPApplication(build_runtime(_project(tmp_path))))

    async def call(name: str, arguments: dict[str, object]) -> dict[str, object]:
        response = await server.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        assert response is not None
        return response

    unknown_field = await call(
        "cortex_precise_definition",
        {"path": "a.py", "line": 1, "column": 1, "surprise": True},
    )
    assert "unknown fields: surprise" in unknown_field["error"]["message"]

    missing = await call("cortex_precise_definition", {"path": "a.py"})
    assert "missing required fields" in missing["error"]["message"]

    wrong_type = await call(
        "cortex_precise_definition", {"path": "a.py", "line": "five", "column": 1}
    )
    assert "must be an integer" in wrong_type["error"]["message"]

    zero_line = await call(
        "cortex_precise_definition", {"path": "a.py", "line": 0, "column": 1}
    )
    assert "must be >= 1" in zero_line["error"]["message"]

    empty_symbol = await call("cortex_symbol_occurrences", {"symbol": ""})
    assert "at least 1 characters" in empty_symbol["error"]["message"]

    no_match = await call(
        "cortex_rewrite_preview",
        {"pattern": "absent_xyz", "replacement": "new", "language": "python"},
    )
    assert no_match["error"]["code"] == -32602
    assert "matched nothing" in no_match["error"]["message"]

    bad_preview = await call("cortex_rewrite_apply", {"preview_id": "../escape"})
    assert bad_preview["error"]["code"] == -32602
    assert "invalid preview id" in bad_preview["error"]["message"]


@pytest.mark.asyncio
async def test_context_tool_fuses_evidence_and_reports_provider_state(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _write_precision_index(root)
    application = _application(root)

    plain = await application.call(
        "cortex_context", {"query": "explain the middleware", "budget": 4096}
    )
    assert plain["providers"] == []
    assert plain["degraded"] is False

    fused = await application.call(
        "cortex_context",
        {
            "query": "migrate the authentication middleware",
            "budget": 8192,
            "path": "src/middleware.py",
            "line": 4,
            "column": 5,
            "library": "framework",
            "pattern": "old_api",
            "language": "python",
        },
    )
    sources = {chunk["source"] for chunk in fused["chunks"]}
    assert "evidence:precision_index" in sources
    assert "evidence:structural" in sources
    states = {item["provider"]: item["state"] for item in fused["providers"]}
    assert states["precision_index"] == "available"
    assert states["dependency_docs"] == "not_configured"
    assert states["structural"] == "available"
    assert fused["degraded"] is True
    assert fused["route"]["layers"]

    exact_chunk = next(
        chunk for chunk in fused["chunks"] if chunk["source"] == "evidence:precision_index"
    )
    assert exact_chunk["metadata"]["trust"] == "exact"
    assert exact_chunk["metadata"]["provenance"] == "precision-index"


@pytest.mark.asyncio
async def test_impact_tool_reports_evidence_quality(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _write_precision_index(root)
    application = _application(root)
    report = await application.call("cortex_impact", {"query": "authenticate"})
    assert "evidence_quality" in report
    assert report["exact_dependents"] >= 1
    assert any(item["exact"] for item in report["direct"])


# -- CLI surface ------------------------------------------------------------


def test_new_cli_commands_work_end_to_end(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _write_precision_index(root)

    status = json.loads(_ok(["precision-status", "--path", str(root)]))
    assert status["status"] == "available"

    definition = json.loads(
        _ok(["definition", "src/routes.py", "5", "12", "--path", str(root)])
    )
    assert definition["evidence"][0]["path"] == "src/middleware.py"

    references = json.loads(
        _ok(["references", "src/middleware.py", "4", "5", "--path", str(root)])
    )
    assert references["evidence"][0]["path"] == "src/routes.py"

    implementations = json.loads(
        _ok(["implementations", "src/middleware.py", "4", "5", "--path", str(root)])
    )
    assert implementations["evidence"] == []

    dependency = json.loads(_ok(["dependency", "framework", "--path", str(root)]))
    assert dependency["dependencies"][0]["resolved_version"] == "2.4.1"

    docs = json.loads(_ok(["dependency-docs", "framework", "middleware", "--path", str(root)]))
    assert docs["documentation_available"] is False

    matches = json.loads(
        _ok(
            [
                "structural-search",
                "--pattern",
                "old_api",
                "--lang",
                "python",
                "--path",
                str(root),
            ]
        )
    )
    assert len(matches["matches"]) == 3

    doctor = _ok(["doctor", "--path", str(root)])
    assert "precision intelligence" in doctor
    assert "dependency docs" in doctor
    assert "structural engine" in doctor


def test_cli_rewrite_preview_and_apply_round_trip(tmp_path: Path) -> None:
    root = _project(tmp_path)
    preview = json.loads(
        _ok(
            [
                "rewrite-preview",
                "--pattern",
                "old_api",
                "--replacement",
                "new_api",
                "--lang",
                "python",
                "--path",
                str(root),
            ]
        )
    )
    assert preview["total_matches"] == 3
    result = json.loads(_ok(["rewrite-apply", preview["preview_id"], "--path", str(root)]))
    assert result["applied"] is True
    assert "new_api" in (root / "src" / "routes.py").read_text(encoding="utf-8")


def test_cli_reports_user_errors_without_a_stack_trace(tmp_path: Path) -> None:
    root = _project(tmp_path)
    for args in (
        ["structural-search", "--pattern", "((((", "--lang", "python", "--path", str(root)],
        [
            "rewrite-preview",
            "--pattern",
            "absent_xyz",
            "--replacement",
            "new",
            "--lang",
            "python",
            "--path",
            str(root),
        ],
        ["rewrite-apply", "00000000000000000000000000000000", "--path", str(root)],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 2, result.stdout
        assert "Traceback" not in result.stdout


# -- end-to-end acceptance scenario ----------------------------------------


@pytest.mark.asyncio
async def test_dependency_sensitive_migration_workflow(tmp_path: Path) -> None:
    """Upgrade the authentication middleware to the API for the resolved version.

    Exercises the full acceptance path: classify, read manifests, locate source,
    resolve exact references, gather documentation state, find structural
    matches, calculate impact, preview, apply, reindex, validate, re-check.
    """
    root = _project(tmp_path)
    _write_precision_index(root)
    application = ExtendedMCPApplication(build_runtime(root))
    request = "Upgrade the authentication middleware to the supported framework API"

    # 1. classify the request
    plan = application.runtime.gateway.route(request, str(root))
    assert "dependency_docs" in plan.evidence_layers

    # 2. dependency versions from manifests and lockfile
    info = await application.call("cortex_dependency_info", {"library": "framework"})
    resolved = info["dependencies"][0]["resolved_version"]
    assert resolved == "2.4.1"

    # 3-4. locate the middleware and resolve exact references to it
    references = await application.call(
        "cortex_precise_references", {"path": "src/middleware.py", "line": 4, "column": 5}
    )
    assert references["exact_results"] == 1
    assert references["evidence"][0]["path"] == "src/routes.py"

    # 5. version-aware documentation, explicitly unavailable offline
    docs = await application.call(
        "cortex_dependency_docs", {"library": "framework", "query": "middleware API"}
    )
    assert docs["documentation_available"] is False
    assert docs["provider"]["fallback"]

    # 6. structural usages of the deprecated API
    matches = await application.call(
        "cortex_structural_search", {"pattern": "old_api", "language": "python"}
    )
    assert len(matches["matches"]) == 3

    # 7. impact, including affected tests
    impact = await application.call("cortex_impact", {"query": "handler"})
    assert "risk_score" in impact

    # 8. compact fused context
    context = await application.call(
        "cortex_context",
        {
            "query": request,
            "budget": 8192,
            "path": "src/middleware.py",
            "line": 4,
            "column": 5,
            "library": "framework",
            "pattern": "old_api",
            "language": "python",
        },
    )
    assert context["chunks"]
    assert context["metrics"]["final_tokens"] <= 8192

    # 9. rewrite preview
    previewed = await application.call(
        "cortex_rewrite_preview",
        {"pattern": "old_api", "replacement": "new_api", "language": "python"},
    )
    preview = previewed["preview"]
    assert preview["total_matches"] == 3
    assert preview["affected_symbols"]

    # 10-11. authorized apply
    result = await application.call(
        "cortex_rewrite_apply", {"preview_id": preview["preview_id"]}
    )

    # 12-15. reindex, validation, post-change impact, and a reported summary
    assert result["applied"] is True
    assert result["files_changed"] == 2
    assert result["matches_applied"] == 3
    assert result["reindexed_files"] >= 1
    assert result["validation"]["passed"] is True
    assert "residual_risk" in result["post_impact"]
    assert "old_api" not in (root / "src" / "routes.py").read_text(encoding="utf-8")

    # the precision index is now older than the sources it described
    status = await application.call("cortex_precision_status", {})
    assert status["status"] == "stale"
    assert status["stale_reason"]

    after = await application.call(
        "cortex_precise_references", {"path": "src/middleware.py", "line": 4, "column": 5}
    )
    assert after["evidence"][0]["exact"] is False
    assert after["evidence"][0]["stale"] is True
    assert after["degraded"] is True
