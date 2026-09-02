"""Repository and symbol history intelligence from local Git metadata."""

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


@dataclass(frozen=True, slots=True)
class SymbolCommit:
    sha: str
    author: str
    email: str
    date: str
    subject: str


@dataclass(frozen=True, slots=True)
class BlameLine:
    line: int
    sha: str
    author: str
    email: str
    timestamp: int | None
    content: str


@dataclass(frozen=True, slots=True)
class SymbolHistory:
    path: str
    start_line: int
    end_line: int
    commits: tuple[SymbolCommit, ...]
    blame: tuple[BlameLine, ...]
    owners: tuple[AuthorActivity, ...]


class GitIntelligence:
    def __init__(self, root: Path, timeout_seconds: float = 15.0) -> None:
        self.root = root.resolve()
        self.timeout_seconds = timeout_seconds

    def _git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root), *args],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
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
            if path:
                current_files.append(path)
                if path not in recent:
                    recent.append(path)
        if commits:
            flush()
        return GitReport(
            commits=commits,
            hot_files=tuple(
                FileActivity(path, count) for path, count in file_changes.most_common(30)
            ),
            co_changes=tuple(
                CoChange(left, right, count)
                for (left, right), count in pair_changes.most_common(30)
            ),
            authors=tuple(
                AuthorActivity(name, email, count)
                for (name, email), count in author_changes.most_common(20)
            ),
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
            if len(parts) == 5:
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

    def symbol_history(self, path: str, start_line: int, end_line: int) -> SymbolHistory:
        if start_line < 1 or end_line < start_line:
            raise ValueError("invalid symbol line range")
        commits = self._symbol_commits(path, start_line, end_line)
        blame = self._blame(path, start_line, end_line)
        ownership: Counter[tuple[str, str]] = Counter(
            (line.author, line.email) for line in blame if line.author
        )
        owners = tuple(
            AuthorActivity(name, email, count) for (name, email), count in ownership.most_common()
        )
        return SymbolHistory(
            path=path,
            start_line=start_line,
            end_line=end_line,
            commits=tuple(commits),
            blame=tuple(blame),
            owners=owners,
        )

    def _symbol_commits(self, path: str, start_line: int, end_line: int) -> list[SymbolCommit]:
        raw = self._git(
            "log",
            "--date=iso-strict",
            "--format=@@C@@%H|%an|%ae|%ad|%s",
            "-L",
            f"{start_line},{end_line}:{path}",
        )
        commits: list[SymbolCommit] = []
        seen: set[str] = set()
        for line in raw.splitlines():
            if not line.startswith("@@C@@"):
                continue
            parts = line[5:].split("|", 4)
            if len(parts) != 5 or parts[0] in seen:
                continue
            seen.add(parts[0])
            commits.append(SymbolCommit(*parts))
        return commits

    def _blame(self, path: str, start_line: int, end_line: int) -> list[BlameLine]:
        raw = self._git(
            "blame",
            "--line-porcelain",
            "-L",
            f"{start_line},{end_line}",
            "--",
            path,
        )
        result: list[BlameLine] = []
        current: dict[str, str] = {}
        current_line = start_line
        for line in raw.splitlines():
            if line.startswith("\t"):
                timestamp = current.get("author-time")
                result.append(
                    BlameLine(
                        line=current_line,
                        sha=current.get("sha", ""),
                        author=current.get("author", ""),
                        email=current.get("author-mail", "").strip("<>"),
                        timestamp=int(timestamp) if timestamp and timestamp.isdigit() else None,
                        content=line[1:],
                    )
                )
                current_line += 1
                current = {}
                continue
            parts = line.split(" ", 1)
            if (
                len(parts) == 2
                and len(parts[0]) >= 7
                and all(char in "0123456789abcdef^" for char in parts[0].lower())
            ):
                current["sha"] = parts[0].lstrip("^")
            elif len(parts) == 2:
                current[parts[0]] = parts[1]
        return result
