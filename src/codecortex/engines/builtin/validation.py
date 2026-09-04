"""Local validation engine."""

from __future__ import annotations

import ast
from pathlib import Path

from codecortex.core.contracts import Engine
from codecortex.core.models import AgentRequest, Capability, ContextChunk, EngineResult


class ValidationEngine(Engine):
    capability = Capability.VALIDATION

    def __init__(self, project_root: Path, max_files: int = 2_000) -> None:
        self.project_root = project_root.resolve()
        self.max_files = max_files

    async def health(self) -> bool:
        return self.project_root.exists() and self.project_root.is_dir()

    async def execute(self, request: AgentRequest) -> EngineResult:
        del request
        checked = 0
        issues: list[str] = []
        for path in self.project_root.rglob("*.py"):
            if checked >= self.max_files:
                break
            if any(
                part in {".git", ".codecortex", ".venv", "venv", "__pycache__"}
                for part in path.parts
            ):
                continue
            checked += 1
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                relative = path.relative_to(self.project_root)
                issues.append(f"{relative}:{exc.lineno}: {exc.msg}")
            except (OSError, UnicodeDecodeError):
                continue

        content = "Python syntax validation passed." if not issues else "\n".join(issues[:100])
        return EngineResult(
            capability=self.capability,
            content=content,
            chunks=[
                ContextChunk(
                    source="validation",
                    content=content,
                    tokens=max(1, len(content) // 4),
                    relevance=0.95,
                    metadata={"issues": len(issues), "checked": checked},
                )
            ],
            metadata={"checked": checked, "issues": len(issues)},
        )
