#!/usr/bin/env python3
"""Record one benchmark result into CodeCortex longitudinal performance history."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from codecortex.distributed.performance import PerformanceHistoryStore


def _flatten_numeric(value: object, prefix: str = "") -> dict[str, float | int | None]:
    output: dict[str, float | int | None] = {}
    if value is None and prefix:
        output[prefix] = None
    elif isinstance(value, bool):
        if prefix:
            output[prefix] = int(value)
    elif isinstance(value, (int, float)):
        if prefix:
            output[prefix] = value
    elif isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            output.update(_flatten_numeric(child, name))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            name = f"{prefix}[{index}]" if prefix else f"[{index}]"
            output.update(_flatten_numeric(child, name))
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--suite", default="production-vanilla")
    parser.add_argument("--commit", default=os.getenv("GITHUB_SHA", "unknown"))
    args = parser.parse_args()

    payload = json.loads(args.result.read_text(encoding="utf-8"))
    metrics = _flatten_numeric(payload)
    store = PerformanceHistoryStore(args.database)
    store.record(
        args.commit,
        args.suite,
        metrics,
        metadata={"source": str(args.result), "github_run_id": os.getenv("GITHUB_RUN_ID", "")},
    )
    store.export_json(args.output)
    print(f"recorded {len(metrics)} numeric metrics to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
