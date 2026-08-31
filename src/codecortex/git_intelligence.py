"""Repository history intelligence built from local Git metadata."""

from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileActivity:
    path: str
    changes: int


@dataclass(frozen=True, slots=True)
class CoChange:
    left: str
    right: str
    commits: int


@dataclass(frozen=True, slots=True)
class AuthorActivity:
    name: str
    email: str
    commits: int


@dataclass(frozen=True, slots=True)
class GitReport:
    commits: int
    hot_files: tuple[FileActivity, ...]
    co_changes: tuple[CoChange, ...]
    authors: tuple[AuthorActivity, ...]
    recent_files: tuple[str, ...]


class GitIntelligence:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root), *args],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            return ""
        return result.stdout if result.returncode == 0 else ""

    def is_repository(self) -> bool:
        return self._git("rev-parse", "--is-inside-work-tree").strip() == "true"

    def analyze(self, limit: int = 500) -> GitReport:
        raw = self._git(
            "log",
            f"-n{max(1, limit)}",
            "--date=iso-strict",
            "--format=@@%H|%an|%ae|%ad",
            "--name-only",
        )
        if not raw:
            return GitReport(0, (), (), (), ())

        file_changes: Counter[str] = Counter()
        pair_changes: Counter[tuple[str, str]] = Counter()
        author_changes: Counter[tuple[str, str]] = Counter()
        recent: list[str] = []
        current_files: list[str] = []
        current_author: tuple[str, str] | None = None
        commits = 0

        def flush() -> None:
            nonlocal current_files, current_author
            unique = sorted(set(current_files))
            file_changes.update(unique)
            for index, left in enumerate(unique):
                for right in unique[index + 1 :]:
                    pair_changes[(left, right)] += 1
            if current_author is not None:
                author_changes[current_author] += 1
            current_files = []
            current_author = None

        for line in raw.splitlines():
            if line.startswith("@@"):
                if commits:
                    flush()
                commits += 1
                parts = line[2:].split("|", 3)
                if len(parts) >= 3:
                    current_author = (parts[1], parts[2])
                continue
            path = line.strip()
            if not path:
                continue
            current_files.append(path)
            if path not in recent:
                recent.append(path)
        if commits:
            flush()

        hot_files = tuple(
            FileActivity(path, changes)
            for path, changes in file_changes.most_common(30)
        )
        co_changes = tuple(
            CoChange(left, right, count)
            for (left, right), count in pair_changes.most_common(30)
        )
        authors = tuple(
            AuthorActivity(name, email, count)
            for (name, email), count in author_changes.most_common(20)
        )
        return GitReport(
            commits=commits,
            hot_files=hot_files,
            co_changes=co_changes,
            authors=authors,
            recent_files=tuple(recent[:50]),
        )

    def file_history(self, path: str, limit: int = 30) -> list[dict[str, str]]:
        raw = self._git(
            "log",
            f"-n{max(1, limit)}",
            "--date=iso-strict",
            "--format=%H|%an|%ae|%ad|%s",
            "--",
            path,
        )
        result: list[dict[str, str]] = []
        for line in raw.splitlines():
            parts = line.split("|", 4)
            if len(parts) != 5:
                continue
            result.append(
                {
                    "sha": parts[0],
                    "author": parts[1],
                    "email": parts[2],
                    "date": parts[3],
                    "subject": parts[4],
                }
            )
        return result
