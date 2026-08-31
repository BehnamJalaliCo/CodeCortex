#!/usr/bin/env python3
"""Exercise one pinned engine through its real CodeCortex contract."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

from codecortex.backends import BACKENDS, BackendManager, ContextBackendAdapter, GraphBackendAdapter, SymbolBackendAdapter
from codecortex.backends.mcp_client import MCPStdioClient


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in BACKENDS:
        print("usage: backend_conformance.py graph|symbols|context", file=sys.stderr)
        return 2
    key = sys.argv[1]
    manager = BackendManager(timeout_seconds=1200, source_root=Path.cwd())
    spec = BACKENDS[key]
    assert manager.local_source_path(spec) is not None, f"{key}: pinned source checkout is missing"
    manager.ensure(spec)
    assert (manager.installation_metadata(spec) or {}).get("source_kind") == "vendored"

    with tempfile.TemporaryDirectory(prefix="codecortex-backend-e2e-") as temp:
        root = Path(temp).resolve()
        shutil.copytree(Path.cwd() / "examples" / "demo_project", root, dirs_exist_ok=True)
        if key == "graph":
            adapter = GraphBackendAdapter(root, manager)
            assert asyncio.run(adapter.health())
            payload = adapter.build()
            serialized = json.dumps(payload, ensure_ascii=False)
            assert payload and "AuthService" in serialized
        elif key == "symbols":
            adapter = SymbolBackendAdapter(root, manager)
            assert asyncio.run(adapter.health())
            adapter.require_tools(adapter.tools(), adapter.required_tools)
            result = adapter.call("find_symbol", {"name_path_pattern": "AuthService", "relative_path": "auth/service.py", "include_body": False})
            assert "AuthService" in (MCPStdioClient.content_text(result) or json.dumps(result))
        else:
            adapter = ContextBackendAdapter(root, manager)
            assert asyncio.run(adapter.health())
            adapter.require_tools(adapter.tools(), adapter.required_tools)
            content = "\n".join(["AuthService refreshes access tokens through TokenStore."] * 80)
            result = adapter.compress(content)
            assert MCPStdioClient.content_text(result).strip()
            assert isinstance(adapter.stats(), dict)

    print(f"{key}: vendored E2E contract verified at {spec.revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
