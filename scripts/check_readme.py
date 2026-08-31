#!/usr/bin/env python3
"""Validate the public README quality envelope used by CI and releases."""

from __future__ import annotations

import re
from pathlib import Path

README = Path("README.md")
MIN_WORDS = 50_000
MAX_BYTES = 500 * 1024
REQUIRED_MARKERS = (
    "## Install from PyPI",
    "pip install --upgrade codecortex-context-engine",
    "## Architecture at a glance",
    "```mermaid",
    "## Remote operation",
    "## Security model",
    "## Maintainer and project ownership",
    "Behnam Jalali",
)


def main() -> int:
    data = README.read_bytes()
    text = data.decode("utf-8")
    words = len(re.findall(r"\b[\w][\w'’-]*\b", text, flags=re.UNICODE))
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if words < MIN_WORDS:
        raise SystemExit(f"README must contain at least {MIN_WORDS:,} words; found {words:,}")
    if len(data) >= MAX_BYTES:
        raise SystemExit(f"README exceeds GitHub's 500 KiB render limit: {len(data):,} bytes")
    if missing:
        raise SystemExit("README is missing required public sections: " + ", ".join(missing))
    print(f"README verified: {words:,} words, {len(data):,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
