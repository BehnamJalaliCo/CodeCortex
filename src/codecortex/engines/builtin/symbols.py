"""Local multi-language symbol intelligence engine using the unified parser registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codecortex.core.contracts import Engine
from codecortex.core.models import AgentRequest, Capability, ContextChunk, EngineResult
from codecortex.languages import LanguageRegistry

_EXCLUDED = {".git", ".codecortex", ".venv", "venv", "node_modules", "__pycache__"}


@dataclass(frozen=True, slots=True)
class IndexedSymbol:
    name: str
    kind: str
    path: Path
    line: int
    language: str
    container: str | None = None


class SymbolEngine(Engine):
    capability = Capability.SYMBOLS

    def __init__(self, project_root: Path, max_files: int = 5_000) -> None:
        self.project_root = project_root.resolve()
        self.max_files = max_files
        self.languages = LanguageRegistry()

    async def health(self) -> bool:
        return self.project_root.exists() and self.project_root.is_dir()

    def _symbols(self) -> list[IndexedSymbol]:
        symbols: list[IndexedSymbol] = []
        count = 0
        for path in self.project_root.rglob("*"):
            if count >= self.max_files:
                break
            if not path.is_file():
                continue
            spec = self.languages.language_for(path)
            if spec is None:
                continue
            relative = path.relative_to(self.project_root)
            if any(part in _EXCLUDED for part in relative.parts):
                continue
            count += 1
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            symbols.extend(
                IndexedSymbol(unit.name, unit.kind, path, unit.line, spec.name, unit.container)
                for unit in self.languages.parse(path, source)
            )
        return symbols

    async def execute(self, request: AgentRequest) -> EngineResult:
        symbols = self._symbols()
        terms = {term.lower().strip(".,:;()[]{}") for term in request.query.split() if len(term) > 2}
        ranked: list[tuple[int, IndexedSymbol]] = []
        for symbol in symbols:
            name = symbol.name.lower()
            path = str(symbol.path.relative_to(self.project_root)).lower()
            score = sum(5 if term == name else 3 if term in name else 1 if term in path else 0 for term in terms)
            if score:
                ranked.append((score, symbol))
        ranked.sort(key=lambda item: (-item[0], item[1].line, item[1].name))
        matches = [symbol for _, symbol in ranked[:50]]
        lines = [f"{symbol.language}:{symbol.kind} {symbol.name} — {symbol.path.relative_to(self.project_root)}:{symbol.line}" for symbol in matches]
        content = "\n".join(lines) if lines else "No matching symbols found."
        languages = sorted({symbol.language for symbol in symbols})
        return EngineResult(
            capability=self.capability,
            content=content,
            chunks=[ContextChunk(source="symbol-index", content=content, tokens=max(1, len(content) // 4), relevance=0.90 if matches else 0.30, metadata={"matches": len(matches), "languages": languages})],
            metadata={"symbols_indexed": len(symbols), "matches": len(matches), "languages": languages},
        )
