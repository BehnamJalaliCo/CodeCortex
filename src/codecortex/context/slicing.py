"""AST-aware source slicing for compact symbol context."""

from __future__ import annotations

import re
from pathlib import Path

from codecortex.context.tokenizer import AutoTokenCounter, TokenCounter
from codecortex.core.models import ContextChunk
from codecortex.languages import LanguageRegistry


class AstContextSlicer:
    """Select complete parsed units before falling back to a bounded line window."""

    def __init__(
        self,
        root: Path,
        token_counter: TokenCounter | None = None,
        *,
        context_lines: int = 2,
    ) -> None:
        self.root = root.resolve()
        self.languages = LanguageRegistry()
        self.token_counter = token_counter or AutoTokenCounter()
        self.context_lines = max(0, context_lines)

    def slice_symbol(
        self,
        path: Path,
        symbol: str,
        line: int | None = None,
        *,
        max_tokens: int = 800,
    ) -> str:
        source = self._read(path)
        if not source:
            return ""
        lines = source.splitlines()
        units = sorted(
            self.languages.parse(path, source),
            key=lambda item: (item.line, item.name),
        )
        candidates = [unit for unit in units if unit.name == symbol]
        if candidates:
            if line is not None:
                unit = min(candidates, key=lambda item: abs(item.line - line))
            else:
                unit = candidates[0]
            start = max(0, unit.line - 1 - self.context_lines)
            if unit.end_line is not None:
                end = min(len(lines), unit.end_line + self.context_lines)
            else:
                following = [item.line for item in units if item.line > unit.line]
                inferred = min(following) - 1 if following else min(len(lines), unit.line + 80)
                end = min(len(lines), inferred + self.context_lines)
            text = "\n".join(lines[start:end])
            return self.token_counter.truncate(text, max(1, max_tokens))

        center = max(1, line or 1)
        start = max(0, center - 12)
        end = min(len(lines), center + 24)
        return self.token_counter.truncate("\n".join(lines[start:end]), max(1, max_tokens))

    def slice(
        self,
        query: str,
        path: Path,
        *,
        max_tokens: int = 1_200,
        limit: int = 6,
    ) -> list[ContextChunk]:
        source = self._read(path)
        if not source:
            return []
        query_terms = {
            term.lower()
            for term in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query)
        }
        units = self.languages.parse(path, source)
        scored: list[tuple[int, object]] = []
        for unit in units:
            haystack = {unit.name.lower(), *(ref.lower() for ref in unit.references)}
            score = sum(4 if term == unit.name.lower() else 1 for term in query_terms if term in haystack)
            if score:
                scored.append((score, unit))
        scored.sort(key=lambda item: (-item[0], item[1].line, item[1].name))  # type: ignore[attr-defined]
        if not scored:
            return []
        per_chunk = max(64, max_tokens // max(1, min(limit, len(scored))))
        result: list[ContextChunk] = []
        for _, unit in scored[: max(1, limit)]:
            content = self.slice_symbol(path, unit.name, unit.line, max_tokens=per_chunk)  # type: ignore[attr-defined]
            if not content:
                continue
            relative = path.resolve().relative_to(self.root).as_posix()
            result.append(
                ContextChunk(
                    source=f"ast:{relative}:{unit.name}",  # type: ignore[attr-defined]
                    content=content,
                    tokens=self.token_counter.count(content),
                    relevance=0.96,
                    metadata={
                        "path": relative,
                        "symbol": unit.name,  # type: ignore[attr-defined]
                        "line": unit.line,  # type: ignore[attr-defined]
                        "end_line": unit.end_line,  # type: ignore[attr-defined]
                        "container": unit.container,  # type: ignore[attr-defined]
                        "ast_slice": True,
                    },
                )
            )
        return result

    @staticmethod
    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""
