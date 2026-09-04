#!/usr/bin/env python3
"""Run the revision-pinned production benchmark matrix."""

from __future__ import annotations

import argparse
from pathlib import Path

from codecortex.evaluation.production import ProductionBenchmarkRunner


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, default=Path("benchmarks/production/spec.json"))
    parser.add_argument("--workspace", type=Path, default=Path(".codecortex/benchmarks/production"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/production/results.json"))
    parser.add_argument(
        "--provision", action="store_true", help="Install pinned mature backends before running"
    )
    parser.add_argument(
        "--scenario",
        action="append",
        choices=["vanilla", "graph", "symbols", "context", "full"],
        help="Run only selected scenario(s); repeat the flag for multiple values",
    )
    args = parser.parse_args()
    runner = ProductionBenchmarkRunner.load(
        args.spec,
        workspace=args.workspace,
        provision_backends=args.provision,
    )
    report = runner.run(args.scenario)
    report.save(args.output)
    print(f"saved {args.output}")
    for scenario, summary in report.summary().items():
        print(scenario, json_line(summary))
    return 0


def json_line(value: object) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"))


if __name__ == "__main__":
    raise SystemExit(main())
