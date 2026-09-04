"""Typed model of an imported precision index."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from codecortex.precision.compatibility import EncodingSource
from codecortex.precision.identity import SymbolIdentity, parse_symbol
from codecortex.precision.schema import PositionEncoding, SymbolRole

#: Prefix marking a symbol whose identity is scoped to one document.
LOCAL_SYMBOL_PREFIX = "local "

#: Separator for document-scoped symbol keys. A NUL cannot appear in a document
#: path or a symbol string, so a scoped key can never collide with a real one.
_SCOPE_SEPARATOR = "\x00"


class PrecisionIndexError(ValueError):
    """Raised when a precision index cannot be imported."""


def is_local_symbol(symbol: str) -> bool:
    """Return whether ``symbol`` is local to a single document.

    The schema reserves the ``local <id>`` form for entities that cannot be
    accessed from outside their document, and the ids restart per document. A
    ``local 1`` in one file is a different entity from ``local 1`` in another.
    """
    return symbol.startswith(LOCAL_SYMBOL_PREFIX)


def scoped_symbol_key(document_path: str, symbol: str) -> str:
    """Return the lookup key that keeps document-local symbols from colliding.

    Global symbols keep their protocol string, so cross-file navigation is
    unaffected. Local symbols are namespaced by the document that owns them.
    """
    if not is_local_symbol(symbol):
        return symbol
    return f"{document_path}{_SCOPE_SEPARATOR}{symbol}"


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
        """Return whether a position falls in this range, per ``[start, end)``.

        The schema defines occurrence ranges as half-open, so a caret at
        ``end_column`` is *outside* the range. That matters wherever two
        identifiers touch: with an inclusive end, ``a`` in ``a.b`` would claim
        the position that belongs to ``.``, and the tightest-range tie-break
        would then be resolving a caret to whichever symbol happened to sort
        first. The caret on the last character of an identifier is
        ``end_column - 1`` and still matches.
        """
        if line < self.start_line or line > self.end_line:
            return False
        if line == self.start_line and column < self.start_column:
            return False
        if line == self.end_line and column >= self.end_column:
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
    #: What the index declared, verbatim. Often ``UNSPECIFIED`` in practice.
    declared_encoding: PositionEncoding = PositionEncoding.UNSPECIFIED
    #: Where the effective encoding came from: the index itself, a measured
    #: record of the producing tool, or an assumption.
    encoding_source: EncodingSource = EncodingSource.ASSUMED
    #: Why, when the encoding was not declared.
    encoding_detail: str = ""
    #: Whether a column read in the effective encoding may be called exact.
    encoding_authoritative: bool = False
    #: Unit occurrence columns are read in. Columns are not Python string
    #: indices unless this is ``UTF32_CODE_UNIT``.
    position_encoding: PositionEncoding = PositionEncoding.UTF32_CODE_UNIT
    #: Document text, retained only when the indexer embedded it. Indexers are
    #: not expected to, so position conversion reads the worktree by default.
    text: str = ""

    @property
    def needs_column_conversion(self) -> bool:
        """Whether occurrence columns may differ from Python character columns.

        Code-point columns need no conversion, but an unverified assumption
        that they *are* code points still has to consult the source line, to
        find out whether the line is ASCII and the assumption therefore moot.
        """
        return (
            self.position_encoding is not PositionEncoding.UTF32_CODE_UNIT
            or not self.encoding_authoritative
        )


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
                key = scoped_symbol_key(occurrence.path, occurrence.symbol)
                by_symbol[key].append(occurrence)
            for symbol in document.symbols:
                key = scoped_symbol_key(document.relative_path, symbol.symbol)
                symbol_info.setdefault(key, symbol)
        for symbol in self.external_symbols:
            # External symbols are by definition not document-local.
            symbol_info.setdefault(symbol.symbol, symbol)
        self._by_path = by_path
        self._by_symbol = dict(by_symbol)
        self._symbol_info = symbol_info

    def _key(self, symbol: str, document: str | None) -> str | None:
        """Return the lookup key for ``symbol``, or None when it cannot be scoped.

        A local symbol is meaningless without the document that owns it, so a
        caller that omits the document gets nothing rather than the union of
        every same-named local across the repository.
        """
        if not is_local_symbol(symbol):
            return symbol
        if document is None:
            return None
        return scoped_symbol_key(document, symbol)

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

    def symbol_information(
        self, symbol: str, document: str | None = None
    ) -> PrecisionSymbol | None:
        key = self._key(symbol, document)
        return self._symbol_info.get(key) if key is not None else None

    def occurrences_for(
        self, symbol: str, document: str | None = None
    ) -> tuple[PrecisionOccurrence, ...]:
        """Return every occurrence of ``symbol``.

        ``document`` scopes the lookup and is required for a document-local
        symbol; for a global symbol it is ignored, since a global symbol's
        occurrences legitimately span files.
        """
        key = self._key(symbol, document)
        return tuple(self._by_symbol.get(key, ())) if key is not None else ()

    def occurrence_at(self, path: str, line: int, column: int) -> PrecisionOccurrence | None:
        """Return the tightest occurrence covering a zero-based position.

        ``column`` must already be expressed in the document's own position
        encoding; see :mod:`codecortex.precision.positions`.
        """
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

    def definitions_for(
        self, symbol: str, document: str | None = None
    ) -> tuple[PrecisionOccurrence, ...]:
        return tuple(
            item for item in self.occurrences_for(symbol, document) if item.is_definition
        )

    def references_for(
        self, symbol: str, document: str | None = None
    ) -> tuple[PrecisionOccurrence, ...]:
        return tuple(
            item for item in self.occurrences_for(symbol, document) if not item.is_definition
        )

    def implementations_for(
        self, symbol: str, document: str | None = None
    ) -> tuple[PrecisionOccurrence, ...]:
        """Return definitions of every symbol that declares it implements ``symbol``.

        A document-local symbol cannot be implemented from outside its
        document, so only global symbols yield cross-file implementers.
        """
        if is_local_symbol(symbol):
            return ()
        implementers: set[tuple[str, str]] = set()
        for key, candidate in self._symbol_info.items():
            for relationship in candidate.relationships:
                if relationship.is_implementation and relationship.symbol == symbol:
                    owner = key.split(_SCOPE_SEPARATOR)[0] if _SCOPE_SEPARATOR in key else ""
                    implementers.add((candidate.symbol, owner))
        results: list[PrecisionOccurrence] = []
        for candidate_symbol, owner in sorted(implementers):
            results.extend(self.definitions_for(candidate_symbol, owner or document))
        return tuple(results)
