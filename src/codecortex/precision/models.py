"""Typed model of an imported precision index."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from codecortex.precision.identity import SymbolIdentity, parse_symbol
from codecortex.precision.schema import SymbolRole


class PrecisionIndexError(ValueError):
    """Raised when a precision index cannot be imported."""


@dataclass(frozen=True, slots=True)
class SourceRange:
    """Half-open source range using zero-based lines and columns, as indexed."""

    start_line: int
    start_column: int
    end_line: int
    end_column: int

    @property
    def single_line(self) -> bool:
        return self.start_line == self.end_line

    def contains(self, line: int, column: int) -> bool:
        if line < self.start_line or line > self.end_line:
            return False
        if line == self.start_line and column < self.start_column:
            return False
        # Ranges are half-open, but a caret sitting on the last character of an
        # identifier must still resolve, so the end column is treated inclusively.
        if line == self.end_line and column > self.end_column:
            return False
        return True

    @property
    def span(self) -> int:
        if self.single_line:
            return max(0, self.end_column - self.start_column)
        return (self.end_line - self.start_line) * 10_000

    def to_dict(self) -> dict[str, int]:
        """Return the range using the one-based convention of the public surface."""
        return {
            "start_line": self.start_line + 1,
            "start_column": self.start_column + 1,
            "end_line": self.end_line + 1,
            "end_column": self.end_column + 1,
        }


@dataclass(frozen=True, slots=True)
class PrecisionOccurrence:
    """One resolved appearance of a symbol inside one indexed document."""

    path: str
    symbol: str
    range: SourceRange
    roles: int = 0

    @property
    def is_definition(self) -> bool:
        return bool(self.roles & SymbolRole.DEFINITION)

    @property
    def is_import(self) -> bool:
        return bool(self.roles & SymbolRole.IMPORT)

    @property
    def is_write(self) -> bool:
        return bool(self.roles & SymbolRole.WRITE_ACCESS)

    @property
    def is_test(self) -> bool:
        return bool(self.roles & SymbolRole.TEST)

    @property
    def is_forward_definition(self) -> bool:
        return bool(self.roles & SymbolRole.FORWARD_DEFINITION)

    def role_names(self) -> tuple[str, ...]:
        return tuple(
            role.name.lower() for role in SymbolRole if self.roles & role and role.name is not None
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "symbol": self.symbol,
            "roles": list(self.role_names()),
            **self.range.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PrecisionRelationship:
    symbol: str
    is_reference: bool = False
    is_implementation: bool = False
    is_type_definition: bool = False
    is_definition: bool = False


@dataclass(frozen=True, slots=True)
class PrecisionSymbol:
    """Metadata the indexer recorded for one symbol."""

    symbol: str
    display_name: str = ""
    kind: int = 0
    documentation: tuple[str, ...] = ()
    relationships: tuple[PrecisionRelationship, ...] = ()
    enclosing_symbol: str = ""

    @property
    def identity(self) -> SymbolIdentity:
        return parse_symbol(self.symbol)

    def to_dict(self) -> dict[str, object]:
        identity = self.identity
        return {
            **identity.to_dict(),
            "documentation": list(self.documentation),
            "enclosing_symbol": self.enclosing_symbol,
            "implementations": [
                item.symbol for item in self.relationships if item.is_implementation
            ],
        }


@dataclass(frozen=True, slots=True)
class PrecisionDocument:
    relative_path: str
    language: str = ""
    occurrences: tuple[PrecisionOccurrence, ...] = ()
    symbols: tuple[PrecisionSymbol, ...] = ()
    text_digest: str = ""


@dataclass(slots=True)
class PrecisionIndex:
    """An imported index with the lookups navigation needs."""

    project_root: str = ""
    tool_name: str = ""
    tool_version: str = ""
    protocol_version: int = 0
    documents: tuple[PrecisionDocument, ...] = ()
    external_symbols: tuple[PrecisionSymbol, ...] = ()

    _by_path: dict[str, PrecisionDocument] = field(default_factory=dict, repr=False)
    _by_symbol: dict[str, list[PrecisionOccurrence]] = field(default_factory=dict, repr=False)
    _symbol_info: dict[str, PrecisionSymbol] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        by_path: dict[str, PrecisionDocument] = {}
        by_symbol: dict[str, list[PrecisionOccurrence]] = defaultdict(list)
        symbol_info: dict[str, PrecisionSymbol] = {}
        for document in self.documents:
            by_path[document.relative_path] = document
            for occurrence in document.occurrences:
                by_symbol[occurrence.symbol].append(occurrence)
            for symbol in document.symbols:
                symbol_info.setdefault(symbol.symbol, symbol)
        for symbol in self.external_symbols:
            symbol_info.setdefault(symbol.symbol, symbol)
        self._by_path = by_path
        self._by_symbol = dict(by_symbol)
        self._symbol_info = symbol_info

    @property
    def document_count(self) -> int:
        return len(self.documents)

    @property
    def symbol_count(self) -> int:
        return len(self._symbol_info)

    @property
    def occurrence_count(self) -> int:
        return sum(len(document.occurrences) for document in self.documents)

    def document(self, path: str) -> PrecisionDocument | None:
        return self._by_path.get(path)

    def paths(self) -> tuple[str, ...]:
        return tuple(self._by_path)

    def symbol_information(self, symbol: str) -> PrecisionSymbol | None:
        return self._symbol_info.get(symbol)

    def occurrences_for(self, symbol: str) -> tuple[PrecisionOccurrence, ...]:
        return tuple(self._by_symbol.get(symbol, ()))

    def occurrence_at(self, path: str, line: int, column: int) -> PrecisionOccurrence | None:
        """Return the tightest occurrence covering a zero-based position."""
        document = self._by_path.get(path)
        if document is None:
            return None
        covering = [
            occurrence
            for occurrence in document.occurrences
            if occurrence.range.contains(line, column)
        ]
        if not covering:
            return None
        return min(covering, key=lambda item: (item.range.span, item.range.start_column))

    def definitions_for(self, symbol: str) -> tuple[PrecisionOccurrence, ...]:
        return tuple(item for item in self.occurrences_for(symbol) if item.is_definition)

    def references_for(self, symbol: str) -> tuple[PrecisionOccurrence, ...]:
        return tuple(item for item in self.occurrences_for(symbol) if not item.is_definition)

    def implementations_for(self, symbol: str) -> tuple[PrecisionOccurrence, ...]:
        """Return definitions of every symbol that declares it implements ``symbol``."""
        implementers = {
            candidate.symbol
            for candidate in self._symbol_info.values()
            for relationship in candidate.relationships
            if relationship.is_implementation and relationship.symbol == symbol
        }
        results: list[PrecisionOccurrence] = []
        for candidate in sorted(implementers):
            results.extend(self.definitions_for(candidate))
        return tuple(results)
