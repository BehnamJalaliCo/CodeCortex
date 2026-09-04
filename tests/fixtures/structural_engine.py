"""A deterministic stand-in for the structural engine binary.

CI must not depend on a third-party binary being installed, so tests drive the
real subprocess code path against this script. It speaks the same argument
vector and newline-delimited JSON the engine does, and it is invoked through
``sys.executable`` so it works identically on POSIX and Windows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

VERSION_LINE = "fake-structural-engine 1.2.3"


def _argument(argv: list[str], flag: str) -> str | None:
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else None


def _matches(root: Path, pattern: str, rewrite: str | None) -> list[dict[str, object]]:
    """Emit one record per literal occurrence of ``pattern`` in the worktree.

    The fake matches a literal needle rather than a real AST pattern: what is
    under test is CodeCortex's adapter, limits, and transaction handling.
    """
    records: list[dict[str, object]] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in {".codecortex", ".git", "__pycache__"} for part in path.parts):
            continue
        try:
            raw = path.read_bytes()
        except OSError:  # pragma: no cover - defensive
            continue
        text = raw.decode("utf-8", errors="replace")
        needle = pattern
        start = 0
        while True:
            index = text.find(needle, start)
            if index == -1:
                break
            start = index + len(needle)
            prefix = text[:index]
            line = prefix.count("\n")
            column = index - (prefix.rfind("\n") + 1)
            byte_start = len(text[:index].encode("utf-8"))
            byte_end = byte_start + len(needle.encode("utf-8"))
            record: dict[str, object] = {
                "text": needle,
                "range": {
                    "byteOffset": {"start": byte_start, "end": byte_end},
                    "start": {"line": line, "column": column},
                    "end": {"line": line, "column": column + len(needle)},
                },
                "file": str(path.relative_to(root).as_posix()),
                "lines": text.splitlines()[line] if line < len(text.splitlines()) else "",
                "language": "Python",
                "metaVariables": {
                    "single": {
                        "NAME": {
                            "text": needle,
                            "range": {
                                "byteOffset": {"start": byte_start, "end": byte_end},
                                "start": {"line": line, "column": column},
                                "end": {"line": line, "column": column + len(needle)},
                            },
                        }
                    },
                    "multi": {},
                    "transformed": {},
                },
            }
            if rewrite is not None:
                record["replacement"] = rewrite
            records.append(record)
    return records


def main(argv: list[str]) -> int:
    if "--version" in argv:
        sys.stdout.write(VERSION_LINE + "\n")
        return 0
    if "run" not in argv:
        sys.stderr.write("unsupported invocation\n")
        return 2
    pattern = _argument(argv, "--pattern") or ""
    language = _argument(argv, "--lang") or ""
    if language == "unsupported-language":
        sys.stderr.write(f"unsupported language: {language}\n")
        return 2
    if pattern == "((((":
        sys.stderr.write("pattern failed to parse\n")
        return 2
    if pattern == "__emit_garbage__":
        sys.stdout.write('{"this is not json\n')
        return 0
    if pattern == "__emit_outside__":
        sys.stdout.write(
            json.dumps(
                {
                    "text": "x",
                    "file": "../outside.py",
                    "range": {
                        "byteOffset": {"start": 0, "end": 1},
                        "start": {"line": 0, "column": 0},
                        "end": {"line": 0, "column": 1},
                    },
                }
            )
            + "\n"
        )
        return 0
    rewrite = _argument(argv, "--rewrite")
    excluded = {
        value.lstrip("!")
        for index, value in enumerate(argv)
        if index and argv[index - 1] == "--globs" and value.startswith("!")
    }
    records = _matches(Path.cwd(), pattern, rewrite)
    kept = [
        record
        for record in records
        if not any(Path(str(record["file"])).match(glob) for glob in excluded)
    ]
    for record in kept:
        sys.stdout.write(json.dumps(record) + "\n")
    return 0 if kept else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
