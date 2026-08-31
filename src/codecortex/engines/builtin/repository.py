"""Local repository intelligence engine."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from codecortex.core.contracts import Engine
from codecortex.core.models import (
    AgentRequest,
    Capability,
    ContextChunk,
    EngineResult,
)

_EXCLUDED_PARTS = {
    ".git",
    ".codecortex",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
}


class RepositoryEngine(Engine):
    capability = Capability.REPOSITORY

    def __init__(self, project_root: Path, max_files: int = 5_000) -> None:
        self.project_root = project_root.resolve()
        self.max_files = max_files

    async def health(self) -> bool:
        return self.project_root.exists() and self.project_root.is_dir()

    def _files(self) -> list[Path]:
        files: list[Path] = []
        for path in self.project_root.rglob("*"):
            if len(files) >= self.max_files:
                break
            if not path.is_file():
                continue
            relative = path.relative_to(self.project_root)
            if any(part in _EXCLUDED_PARTS for part in relative.parts):
                continue
            files.append(path)
        return files

    async def execute(self, request: AgentRequest) -> EngineResult:
        files = self._files()
        relative_files = [path.relative_to(self.project_root) for path in files]
        extension_counts = Counter(path.suffix.lower() or "[no extension]" for path in relative_files)
        terms = {term.lower().strip(".,:;()[]{}") for term in request.query.split() if len(term) > 2}

        ranked: list[tuple[int, Path]] = []
        for path in relative_files:
            value = str(path).lower()
            score = sum(2 if term in path.name.lower() else 1 for term in terms if term in value)
            if score:
                ranked.append((score, path))
        ranked.sort(key=lambda item: (-item[0], len(str(item[1]))))
        matches = [path for _, path in ranked[:30]]

        summary = [
            f"Project root: {self.project_root}",
            f"Files scanned: {len(files)}",
            "Top file types: "
            + ", ".join(f"{suffix}={count}" for suffix, count in extension_counts.most_common(10)),
        ]
        if matches:
            summary.append("Relevant paths:\n" + "\n".join(f"- {path}" for path in matches))

        content = "\n".join(summary)
        return EngineResult(
            capability=self.capability,
            content=content,
            chunks=[
                ContextChunk(
                    source="repository-map",
                    content=content,
                    tokens=max(1, len(content) // 4),
                    relevance=0.80,
                    metadata={"file_count": len(files)},
                )
            ],
            metadata={
                "file_count": len(files),
                "truncated": len(files) >= self.max_files,
                "matches": [str(path) for path in matches],
            },
        )
