"""Which files on disk count as "the repository".

The walk used to be a bare ``rglob`` filtered by a hard-coded directory set.
That set cannot know what a given project considers generated, vendored or
throwaway, so anything the project already declared uninteresting in
``.gitignore`` was indexed anyway: build output, caches, and — the case that
made this visible — eight full agent worktrees checked out under a dot
directory, which turned a 3.5k-file repository into a 15.5k-file one and made
every impact result list the same symbol repeatedly, once per copy.

Git already answers this question exactly, so when the root is a Git work tree
its answer is used: tracked files plus untracked-but-not-ignored ones, which is
also what a contributor sees. Nested checkouts drop out for free because Git
does not descend into them. Everything else (no Git, no ``git`` binary, a
timeout) falls back to the previous walk, so behaviour is unchanged off Git.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

#: Directories never indexed, whatever Git says about them.
EXCLUDED_PARTS = frozenset(
    {".git", ".codecortex", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}
)

#: Git may be slow on a cold cache over a huge tree; do not hang the indexer.
GIT_TIMEOUT_SECONDS = 20.0


def is_excluded(relative: Path) -> bool:
    """True when a repository-relative path lives under an excluded directory."""
    return any(part in EXCLUDED_PARTS for part in relative.parts)


def _git_files(root: Path) -> list[Path] | None:
    """Files Git would show for ``root``, or None when Git cannot answer."""
    try:
        completed = subprocess.run(  # noqa: S603,S607 - fixed argv, no shell
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    names = completed.stdout.decode("utf-8", errors="replace").split("\0")
    return [root / name for name in names if name]


def iter_repository_files(root: Path, *, max_bytes: int | None = None) -> list[Path]:
    """Return the repository's files, sorted, honouring ``.gitignore`` when possible."""
    candidates = _git_files(root)
    if candidates is None:
        candidates = [path for path in root.rglob("*")]
    files: list[Path] = []
    for path in candidates:
        try:
            if not path.is_file():
                continue
            relative = path.relative_to(root)
        except (OSError, ValueError):
            continue
        if is_excluded(relative):
            continue
        if max_bytes is not None:
            try:
                if path.stat().st_size > max_bytes:
                    continue
            except OSError:
                continue
        files.append(path)
    return sorted(files)
