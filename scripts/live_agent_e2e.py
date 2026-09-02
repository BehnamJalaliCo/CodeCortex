#!/usr/bin/env python3
"""Run a real coding-agent CLI and prove that it called CodeCortex over MCP."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--path", default=".")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    root = Path(args.path).resolve()
    events = root / ".codecortex" / "runtime" / "events.jsonl"
    before = events.read_text(encoding="utf-8").splitlines() if events.exists() else []
    prompt = (
        "Use the CodeCortex MCP tool cortex_stats exactly once. "
        "Then answer with the exact text CODECORTEX_E2E_OK and nothing else."
    )
    command = [part.replace("{prompt}", prompt) for part in shlex.split(args.command)]
    env = {**os.environ, "CODECORTEX_E2E_AGENT": args.agent}
    completed = subprocess.run(
        command,
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=args.timeout,
        check=False,
    )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    if completed.returncode != 0:
        return completed.returncode

    after = events.read_text(encoding="utf-8").splitlines() if events.exists() else []
    new_lines = after[len(before) :]
    called = False
    for line in new_lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            payload.get("name") == "mcp.tool.called"
            and payload.get("attributes", {}).get("tool") == "cortex_stats"
        ):
            called = True
            break
    if not called:
        print("agent completed but no cortex_stats MCP call was observed", file=sys.stderr)
        return 3
    if "CODECORTEX_E2E_OK" not in completed.stdout:
        print("agent used MCP but did not complete the expected response", file=sys.stderr)
        return 4
    print(f"{args.agent}: live MCP E2E passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
