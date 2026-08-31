#!/usr/bin/env python3
"""Provision one pinned backend and verify its public CodeCortex contract."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from codecortex.backends import (
    BACKENDS,
    BackendManager,
    ContextBackendAdapter,
    GraphBackendAdapter,
    SymbolBackendAdapter,
)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in BACKENDS:
        print("usage: backend_conformance.py graph|symbols|context", file=sys.stderr)
        return 2
    key = sys.argv[1]
    root = Path.cwd().resolve()
    manager = BackendManager(timeout_seconds=900)
    spec = BACKENDS[key]
    manager.ensure(spec)
    if key == "graph":
        adapter = GraphBackendAdapter(root, manager)
        assert asyncio.run(adapter.health())
        result = manager.run(spec, ("--help",), cwd=root, timeout_seconds=60)
        assert result.returncode == 0
    elif key == "symbols":
        adapter = SymbolBackendAdapter(root, manager)
        assert asyncio.run(adapter.health())
        adapter.require_tools(adapter.tools(), adapter.required_tools)
    else:
        adapter = ContextBackendAdapter(root, manager)
        assert asyncio.run(adapter.health())
        adapter.require_tools(adapter.tools(), adapter.required_tools)
    print(f"{key}: contract verified at {spec.revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
