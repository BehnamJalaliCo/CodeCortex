#!/usr/bin/env python3
"""Provision one pinned backend and exercise its real CodeCortex contract."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

from codecortex.backends import (
    BACKENDS,
    BackendManager,
    ContextBackendAdapter,
    GraphBackendAdapter,
    SymbolBackendAdapter,
)
from codecortex.backends.mcp_client import MCPStdioClient


def _workspace() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix="codecortex-backend-e2e-")


def _copy_fixture(destination: Path) -> None:
    source = Path.cwd() / "examples" / "demo_project"
    shutil.copytree(source, destination, dirs_exist_ok=True)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in BACKENDS:
        print("usage: backend_conformance.py graph|symbols|context", file=sys.stderr)
        return 2
    key = sys.argv[1]
    manager = BackendManager(timeout_seconds=1200)
    spec = BACKENDS[key]
    manager.ensure(spec)

    with _workspace() as temp:
        root = Path(temp).resolve()
        _copy_fixture(root)
        if key == "graph":
            adapter = GraphBackendAdapter(root, manager)
            assert asyncio.run(adapter.health())
            payload = adapter.build()
            assert payload, "graph backend returned an empty graph"
            serialized = json.dumps(payload, ensure_ascii=False)
            assert "AuthService" in serialized, "graph did not index fixture symbols"
            print(f"graph: built fixture graph ({len(serialized)} chars)")
        elif key == "symbols":
            adapter = SymbolBackendAdapter(root, manager)
            assert asyncio.run(adapter.health())
            tools = adapter.tools()
            adapter.require_tools(tools, adapter.required_tools)
            result = adapter.call(
                "find_symbol",
                {
                    "name_path_pattern": "AuthService",
                    "relative_path": "auth/service.py",
                    "include_body": False,
                },
            )
            text = MCPStdioClient.content_text(result) or json.dumps(result)
            assert "AuthService" in text, "symbol backend did not resolve fixture symbol"
            print("symbols: resolved AuthService through live MCP/LSP")
        else:
            adapter = ContextBackendAdapter(root, manager)
            assert asyncio.run(adapter.health())
            tools = adapter.tools()
            adapter.require_tools(tools, adapter.required_tools)
            content = "\n".join(["AuthService refreshes access tokens through TokenStore."] * 80)
            result = adapter.compress(content)
            text = MCPStdioClient.content_text(result)
            assert text.strip(), "context backend returned empty compression"
            stats = adapter.stats()
            assert isinstance(stats, dict), "context backend stats must be an object"
            print(f"context: compressed live payload from {len(content)} to {len(text)} chars")

    print(f"{key}: E2E contract verified at {spec.revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
