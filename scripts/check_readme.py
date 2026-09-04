#!/usr/bin/env python3
"""Validate the public README quality envelope used by CI and releases.

The README is bilingual (English and Persian) and deliberately narrative rather
than exhaustive: reference material lives under ``docs/``. The checks below
therefore assert *structure and coverage* — that both language sections exist,
that install, architecture, security, and ownership are all present in each, and
that the file still renders on GitHub — rather than rewarding length.
"""

from __future__ import annotations

import re
from pathlib import Path

README = Path("README.md")

#: Floor guarding against an accidentally gutted README, not a length target.
MIN_WORDS = 5_000

#: GitHub stops rendering Markdown at 512 KiB.
MAX_BYTES = 500 * 1024

#: Anchors that must exist so both language sections stay navigable.
REQUIRED_MARKERS = (
    "🇬🇧 English",
    "🇮🇷 فارسی",
    '<a id="english"></a>',
    '<a id="فارسی"></a>',
)

#: Sections every reader must be able to find, in English and in Persian.
REQUIRED_ENGLISH_SECTIONS = (
    "## Install",
    "# Architecture",
    "# Security model",
    "# MCP: one agent-facing surface",
    "# Distributed operation",
    "# Evidence Fusion Layer",
    "# Maintainer, contribution, and license",
)
REQUIRED_PERSIAN_SECTIONS = (
    "## نصب",
    "# معماری سیستم",
    "# مدل امنیت",
    "# لایه Evidence Fusion",
    "# نگهداری، مشارکت و License",
)

#: Facts the published README must continue to state.
REQUIRED_FACTS = (
    "pip install --upgrade codecortex-context-engine",
    "```mermaid",
    "Behnam Jalali",
)


def main() -> int:
    data = README.read_bytes()
    text = data.decode("utf-8")
    words = len(re.findall(r"\b[\w][\w'’-]*\b", text, flags=re.UNICODE))

    if len(data) >= MAX_BYTES:
        raise SystemExit(f"README exceeds GitHub's 500 KiB render limit: {len(data):,} bytes")
    if words < MIN_WORDS:
        raise SystemExit(f"README must contain at least {MIN_WORDS:,} words; found {words:,}")

    english, _, persian = text.partition('<a id="فارسی"></a>')
    problems: list[str] = []
    problems += [f"missing marker: {item}" for item in REQUIRED_MARKERS if item not in text]
    problems += [f"missing fact: {item}" for item in REQUIRED_FACTS if item not in text]
    problems += [
        f"missing English section: {item}"
        for item in REQUIRED_ENGLISH_SECTIONS
        if item not in english
    ]
    problems += [
        f"missing Persian section: {item}"
        for item in REQUIRED_PERSIAN_SECTIONS
        if item not in persian
    ]
    if not persian.strip():
        problems.append("the Persian section is empty")
    if problems:
        raise SystemExit("README validation failed:\n  - " + "\n  - ".join(problems))

    print(f"README verified: {words:,} words, {len(data):,} bytes, both language sections present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
