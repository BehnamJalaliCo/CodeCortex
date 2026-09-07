#!/usr/bin/env python3
"""Prepare and collect a reproducible SWE-bench Verified A/B run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DATASET = "SWE-bench/SWE-bench_Verified"


def run(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=check,
    )


def load_instance(instance_id: str) -> dict[str, Any]:
    from datasets import load_dataset

    dataset = load_dataset(DATASET, split="test")
    for row in dataset:
        if row["instance_id"] == instance_id:
            return {
                "instance_id": row["instance_id"],
                "repo": row["repo"],
                "base_commit": row["base_commit"],
                "problem_statement": row["problem_statement"],
                "version": row.get("version"),
                "difficulty": row.get("difficulty"),
            }
    raise SystemExit(f"instance not found in {DATASET}: {instance_id}")


def select_instances(count: int, seed: str, explicit: str) -> list[str]:
    if count <= 0:
        selected = json.loads(explicit)
        if not isinstance(selected, list) or not all(isinstance(item, str) for item in selected):
            raise SystemExit("--explicit must be a JSON list of instance IDs")
        return selected

    from datasets import load_dataset

    dataset = load_dataset(DATASET, split="test")
    ranked = sorted(
        dataset,
        key=lambda row: hashlib.sha256(
            f"{seed}:{row['instance_id']}".encode()
        ).hexdigest(),
    )
    selected: list[str] = []
    seen_repos: set[str] = set()
    for row in ranked:
        instance_id = str(row["instance_id"])
        repo = str(row["repo"])
        if instance_id == "sympy__sympy-20590":
            continue
        if repo in seen_repos:
            continue
        selected.append(instance_id)
        seen_repos.add(repo)
        if len(selected) == count:
            break
    if len(selected) < count:
        raise SystemExit(
            f"requested {count} unique-repository tasks but only found {len(selected)}"
        )
    return selected


def prepare(instance_id: str, workspace: Path) -> None:
    workspace = workspace.resolve()
    target = workspace / "target"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        import shutil
        shutil.rmtree(target)

    item = load_instance(instance_id)
    target.mkdir()
    run("git", "init", "-q", cwd=target)
    run("git", "remote", "add", "origin", f"https://github.com/{item['repo']}.git", cwd=target)
    run("git", "fetch", "-q", "--depth", "1", "origin", item["base_commit"], cwd=target)
    run("git", "checkout", "-q", "--detach", item["base_commit"], cwd=target)

    info_exclude = target / ".git" / "info" / "exclude"
    with info_exclude.open("a", encoding="utf-8") as handle:
        handle.write("\n.codecortex/\n.codex/\n")

    prompt = f"""You are solving one SWE-bench Verified issue.

Repository: {item['repo']}
Base commit: {item['base_commit']}
Instance: {item['instance_id']}

Issue:
{item['problem_statement']}

Rules:
- Work only from this checked-out repository and the issue text above.
- Do not browse the web, search for the original pull request, or look for a gold/reference patch.
- Inspect the repository and implement the smallest correct fix.
- Use all repository-intelligence tools that are available to you.
- If CodeCortex MCP tools are available, you MUST use CodeCortex for at least one repository-navigation or evidence query before editing. If CodeCortex is unavailable, continue with normal local tools.
- Do not change tests unless the issue explicitly requires a test-only change.
- Do not create benchmark metadata files in the repository.
- Do not commit changes.
- You may run local commands and tests.
- Finish with the repository left in the state that contains your proposed fix.
"""
    (workspace / "prompt.txt").write_text(prompt, encoding="utf-8")
    (workspace / "metadata.json").write_text(json.dumps(item, indent=2) + "\n", encoding="utf-8")
    print(f"prepared {instance_id} at {target}")


def read_events(target: Path) -> dict[str, Any]:
    events = target / ".codecortex" / "runtime" / "events.jsonl"
    tools: dict[str, int] = {}
    calls = 0
    if not events.exists():
        return {"mcp_tool_calls": 0, "mcp_tools": {}}
    for line in events.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("name") != "mcp.tool.called":
            continue
        tool = str(payload.get("attributes", {}).get("tool", "unknown"))
        calls += 1
        tools[tool] = tools.get(tool, 0) + 1
    return {"mcp_tool_calls": calls, "mcp_tools": tools}


def collect(workspace: Path, output: Path, mode: str, model: str, effort: str) -> None:
    workspace = workspace.resolve()
    target = workspace / "target"
    metadata = json.loads((workspace / "metadata.json").read_text(encoding="utf-8"))
    base_commit = metadata["base_commit"]

    run("git", "add", "-N", ".", cwd=target, check=False)
    patch = run("git", "diff", "--binary", base_commit, cwd=target).stdout
    status = run("git", "status", "--short", cwd=target).stdout
    event_summary = read_events(target)

    output.mkdir(parents=True, exist_ok=True)
    prediction = [
        {
            "instance_id": metadata["instance_id"],
            "model_patch": patch,
            "model_name_or_path": f"{model}+codex+{mode}",
        }
    ]
    prediction_path = output / f"{mode}-{metadata['instance_id']}.prediction.json"
    prediction_path.write_text(json.dumps(prediction, indent=2) + "\n", encoding="utf-8")

    evidence = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "dataset": DATASET,
        "instance_id": metadata["instance_id"],
        "repo": metadata["repo"],
        "base_commit": base_commit,
        "mode": mode,
        "model": model,
        "reasoning_effort": effort,
        "codecortex_commit": os.environ.get("GITHUB_SHA"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
        "patch_bytes": len(patch.encode()),
        "git_status": status.splitlines(),
        **event_summary,
    }
    evidence_path = output / f"{mode}-{metadata['instance_id']}.evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"saved {prediction_path}")
    print(f"saved {evidence_path}")
    if mode == "codecortex" and event_summary["mcp_tool_calls"] < 1:
        raise SystemExit(
            "invalid CodeCortex treatment run: no CodeCortex MCP tool call was observed"
        )


def combine(source: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"schema_version": 1, "modes": {}}
    for mode in ("baseline", "codecortex"):
        predictions: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        for path in sorted(source.rglob(f"{mode}-*.prediction.json")):
            predictions.extend(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(source.rglob(f"{mode}-*.evidence.json")):
            evidence.append(json.loads(path.read_text(encoding="utf-8")))
        (output / f"predictions-{mode}.json").write_text(
            json.dumps(predictions, indent=2) + "\n", encoding="utf-8"
        )
        summary["modes"][mode] = {
            "predictions": len(predictions),
            "non_empty_patches": sum(bool(row.get("model_patch")) for row in predictions),
            "evidence": evidence,
        }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sel = sub.add_parser("select")
    sel.add_argument("--count", type=int, required=True)
    sel.add_argument("--seed", required=True)
    sel.add_argument("--explicit", required=True)
    sel.add_argument("--github-output", type=Path)

    prep = sub.add_parser("prepare")
    prep.add_argument("--instance-id", required=True)
    prep.add_argument("--workspace", type=Path, required=True)

    col = sub.add_parser("collect")
    col.add_argument("--workspace", type=Path, required=True)
    col.add_argument("--output", type=Path, required=True)
    col.add_argument("--mode", choices=("baseline", "codecortex"), required=True)
    col.add_argument("--model", required=True)
    col.add_argument("--effort", required=True)

    comb = sub.add_parser("combine")
    comb.add_argument("--source", type=Path, required=True)
    comb.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "select":
        selected = select_instances(args.count, args.seed, args.explicit)
        payload = json.dumps(selected, separators=(",", ":"))
        print(payload)
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as handle:
                handle.write(f"instance_ids={payload}\n")
    elif args.command == "prepare":
        prepare(args.instance_id, args.workspace)
    elif args.command == "collect":
        collect(args.workspace, args.output, args.mode, args.model, args.effort)
    else:
        combine(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
