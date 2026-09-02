"""Local multi-language symbol intelligence backed by the shared repository graph."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codecortex.core.contracts import Engine
from codecortex.core.models import AgentRequest, Capability, ContextChunk, EngineResult
from codecortex.projects import RepositoryContext


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

    def __init__(
        self,
        project_root: Path,
        max_files: int = 5_000,
        *,
        context: RepositoryContext | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.max_files = max_files
        self.context = context or RepositoryContext(self.project_root)

    async def health(self) -> bool:
        return self.project_root.exists() and self.project_root.is_dir()

    def _symbols(self) -> list[IndexedSymbol]:
        symbols: list[IndexedSymbol] = []
        for node in self.context.symbols():
            if not node.path:
                continue
            metadata = node.metadata
            symbols.append(
                IndexedSymbol(
                    name=node.name,
                    kind=node.kind,
                    path=self.project_root / node.path,
                    line=node.line or 1,
                    language=str(metadata.get("language", "unknown")),
                    container=None if metadata.get("container") is None else str(metadata["container"]),
                )
            )
        return symbols

    async def execute(self, request: AgentRequest) -> EngineResult:
        symbols = self._symbols()
        terms = {
            term.lower().strip(".,:;()[]{}")
            for term in request.query.split()
            if len(term) > 2
        }
        ranked: list[tuple[int, IndexedSymbol]] = []
        for symbol in symbols:
            name = symbol.name.lower()
            path = str(symbol.path.relative_to(self.project_root)).lower()
            score = sum(
                5 if term == name else 3 if term in name else 1 if term in path else 0
                for term in terms
            )
            if score:
                ranked.append((score, symbol))
        ranked.sort(key=lambda item: (-item[0], item[1].line, item[1].name))
        matches = [symbol for _, symbol in ranked[:50]]
        lines = [
            f"{symbol.language}:{symbol.kind} {symbol.name} — "
            f"{symbol.path.relative_to(self.project_root)}:{symbol.line}"
            for symbol in matches
        ]
        content = "\n".join(lines) if lines else "No matching symbols found."
        languages = sorted({symbol.language for symbol in symbols})
        return EngineResult(
            capability=self.capability,
            content=content,
            chunks=[
                ContextChunk(
                    source="symbol-index",
                    content=content,
                    tokens=max(1, len(content) // 4),
                    relevance=0.90 if matches else 0.30,
                    metadata={"matches": len(matches), "languages": languages},
                )
            ],
            metadata={
                "symbols_indexed": len(symbols),
                "matches": len(matches),
                "languages": languages,
            },
        )
