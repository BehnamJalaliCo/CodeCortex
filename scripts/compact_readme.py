#!/usr/bin/env python3
"""Compact the generated README so GitHub renders it without truncation."""

from __future__ import annotations

import re
from pathlib import Path

README = Path("README.md")
KEEP_PLAYBOOKS = 80
MIN_WORDS = 50_000
MAX_BYTES = 500 * 1024
OUTRO_MARKER = "\n## Maintainer and project ownership\n"


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w][\w'’-]*\b", text, flags=re.UNICODE))


def main() -> int:
    text = README.read_text(encoding="utf-8")
    outro_at = text.find(OUTRO_MARKER)
    if outro_at < 0:
        raise SystemExit("README outro marker not found")

    next_playbook = re.search(rf"(?m)^### {KEEP_PLAYBOOKS + 1}\. ", text)
    if next_playbook is None:
        raise SystemExit(f"playbook {KEEP_PLAYBOOKS + 1} not found")

    cut_at = next_playbook.start()
    previous_playbook = text.rfind(f"\n### {KEEP_PLAYBOOKS}. ", 0, cut_at)
    if previous_playbook < 0:
        raise SystemExit(f"playbook {KEEP_PLAYBOOKS} not found")

    # Avoid leaving an empty archetype heading that belongs only to the discarded section.
    trailing_heading = text.rfind("\n## ", previous_playbook, cut_at)
    if trailing_heading > previous_playbook:
        cut_at = trailing_heading

    compact = text[:cut_at].rstrip() + "\n" + text[outro_at:]
    words = word_count(compact)
    size = len(compact.encode("utf-8"))
    if words < MIN_WORDS:
        raise SystemExit(f"README must contain at least {MIN_WORDS:,} words; found {words:,}")
    if size >= MAX_BYTES:
        raise SystemExit(f"README must stay below {MAX_BYTES:,} bytes; found {size:,}")

    README.write_text(compact, encoding="utf-8")
    print(f"compacted README.md to {words:,} words and {size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
