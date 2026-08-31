"""Local symbol intelligence engine."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from codecortex.core.contracts import Engine
from codecortex.core.models import AgentRequest, Capability, ContextChunk, EngineResult


@dataclass(slots=True)
class Symbol:
    name: str
    kind: str
    path: Path
    line: int


class SymbolEngine(Engine):
    capability = Capability.SYMBOLS

    def __init__(self, project_root: Path, max_files: int = 2_000) -> None:
        self.project_root = project_root.resolve()
        self.max_files = max_files

    async def health(self) -> bool:
        return self.project_root.exists() and self.project_root.is_dir()

    def _python_symbols(self) -> list[Symbol]:
        symbols: list[Symbol] = []
        count = 0
        for path in self.project_root.rglob("*.py"):
            if count >= self.max_files:
                break
            if any(part in {".git", ".codecortex", ".venv", "venv", "__pycache__"} for part in path.parts):
                continue
            count += 1
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(path))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    symbols.append(Symbol(node.name, "class", path, node.lineno))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    kind = "async function" if isinstance(node, ast.AsyncFunctionDef) else "function"
                    symbols.append(Symbol(node.name, kind, path, node.lineno))
        return symbols

    async def execute(self, request: AgentRequest) -> EngineResult:
        symbols = self._python_symbols()
        terms = {term.lower().strip(".,:;()[]{}") for term in request.query.split() if len(term) > 2}

        ranked: list[tuple[int, Symbol]] = []
        for symbol in symbols:
            name = symbol.name.lower()
            path = str(symbol.path.relative_to(self.project_root)).lower()
            score = sum(
                4 if term == name else 3 if term in name else 1 if term in path else 0
                for term in terms
            )
            if score:
                ranked.append((score, symbol))
        ranked.sort(key=lambda item: (-item[0], item[1].line))
        matches = [symbol for _, symbol in ranked[:40]]

        lines = [
            f"{symbol.kind} {symbol.name} — {symbol.path.relative_to(self.project_root)}:{symbol.line}"
            for symbol in matches
        ]
        content = "\n".join(lines) if lines else "No matching symbols found in the current local index."
        return EngineResult(
            capability=self.capability,
            content=content,
            chunks=[
                ContextChunk(
                    source="symbol-index",
                    content=content,
                    tokens=max(1, len(content) // 4),
                    relevance=0.90 if matches else 0.30,
                    metadata={"matches": len(matches)},
                )
            ],
            metadata={"symbols_indexed": len(symbols), "matches": len(matches)},
        )
