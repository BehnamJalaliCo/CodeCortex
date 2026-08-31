#!/usr/bin/env python3
"""Deterministic local demo; prints measured repository intelligence only."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from codecortex.indexing.impact import ImpactAnalyzer
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.runtime import build_runtime
from codecortex.setup import ProjectSetup


async def main() -> None:
    root = (Path(__file__).parent.parent / "examples" / "demo_project").resolve()
    os.environ["CODECORTEX_BACKENDS"] = "builtin"
    setup = ProjectSetup(root).run()
    print(f"Indexed {setup.index.tracked} files / {setup.symbols} symbols")
    graph, _ = IncrementalGraphIndex(root).refresh()
    impact = ImpactAnalyzer(graph).analyze("AuthService")
    print(f"Impact risk: {impact.risk_score:.3f}; direct={len(impact.direct)} indirect={len(impact.indirect)}")
    runtime = build_runtime(root)
    result = await runtime.gateway.query("Find AuthService and explain token refresh", str(root))
    print(f"Route: {', '.join(cap.value for cap in result.plan.selected)}")
    print(f"Context tokens: {result.context_tokens}")
    print(f"Trace: {result.metadata.get('trace_id')}")


if __name__ == "__main__":
    asyncio.run(main())
