#!/usr/bin/env python3
"""Run a real coding-agent command against every production benchmark scenario.

The command must implement the JSON protocol documented in benchmarks/production/README.md.
No token or cost value is inferred when the command does not report it.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from codecortex.evaluation.production import (
    InstrumentedAgentRunner,
    RepositoryCheckout,
    load_repository_specs,
)

SCENARIOS = ("vanilla", "graph", "symbols", "context", "full")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True)
    parser.add_argument("--spec", type=Path, default=Path("benchmarks/production/spec.json"))
    parser.add_argument("--workspace", type=Path, default=Path(".codecortex/benchmarks/agent"))
    parser.add_argument(
        "--output", type=Path, default=Path("benchmarks/production/agent-results.json")
    )
    args = parser.parse_args()
    agent = InstrumentedAgentRunner(args.command)
    specs = load_repository_specs(args.spec)
    checkout = RepositoryCheckout(args.workspace / "repositories")
    rows: list[dict[str, object]] = []
    for repo in specs:
        root = checkout.ensure(repo)
        for case in repo.cases:
            for scenario in SCENARIOS:
                started = perf_counter()
                try:
                    result = agent.run(scenario=scenario, repository=root, case=case)
                    rows.append(
                        {
                            "repository": repo.name,
                            "revision": repo.revision,
                            "case_id": case.id,
                            "scenario": scenario,
                            "wall_time_ms": (perf_counter() - started) * 1000,
                            **asdict(result),
                        }
                    )
                except Exception as exc:
                    rows.append(
                        {
                            "repository": repo.name,
                            "revision": repo.revision,
                            "case_id": case.id,
                            "scenario": scenario,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"schema_version": 1, "results": rows}, indent=2) + "\n", encoding="utf-8"
    )
    print(f"saved {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
