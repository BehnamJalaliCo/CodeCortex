#!/usr/bin/env python3
"""Apply the Windows compatibility fixes discovered by the 0.1.0a2 release matrix."""

from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected patch target not found in {path}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/codecortex/distributed/vector_store.py",
    '''    if scheme == "sqlite":\n        raw_path = unquote(parsed.path)\n        if parsed.netloc:\n            raw_path = f"//{parsed.netloc}{raw_path}"\n        if not raw_path:\n            raise ValueError("sqlite URI requires a path")\n        return SQLiteVectorStore(Path(raw_path))\n''',
    '''    if scheme == "sqlite":\n        raw_path = unquote(parsed.path)\n        netloc = unquote(parsed.netloc)\n        if netloc:\n            if len(netloc) == 2 and netloc[0].isalpha() and netloc[1] == ":":\n                raw_path = f"{netloc}{raw_path}"\n            elif netloc != "localhost":\n                raw_path = f"//{netloc}{raw_path}"\n        if raw_path.startswith("/") and len(raw_path) >= 3:\n            if raw_path[1].isalpha() and raw_path[2] == ":":\n                raw_path = raw_path[1:]\n        if not raw_path:\n            raise ValueError("sqlite URI requires a path")\n        return SQLiteVectorStore(Path(raw_path))\n''',
)

replace_once(
    "src/codecortex/evaluation/production.py",
    '''    def __init__(self, command: str, *, timeout_seconds: float = 900.0) -> None:\n        self.argv = tuple(shlex.split(command))\n        if not self.argv:\n            raise ValueError("agent command is empty")\n        self.timeout_seconds = timeout_seconds\n''',
    '''    def __init__(self, command: str, *, timeout_seconds: float = 900.0) -> None:\n        parts = shlex.split(command, posix=os.name != "nt")\n        if os.name == "nt":\n            parts = [\n                part[1:-1]\n                if len(part) >= 2 and part[0] == part[-1] and part[0] in {"\\\"", "'"}\n                else part\n                for part in parts\n            ]\n        self.argv = tuple(parts)\n        if not self.argv:\n            raise ValueError("agent command is empty")\n        self.timeout_seconds = timeout_seconds\n''',
)

replace_once(
    "pyproject.toml",
    'version = "0.1.0a2"',
    'version = "0.1.0a3"',
)

print("Applied Windows path/command compatibility fixes and prepared v0.1.0a3.")
