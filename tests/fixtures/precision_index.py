"""Build deterministic precision-index fixtures using the real binary encoding.

Tests must exercise the actual wire format rather than a Python stand-in, so
these helpers serialize fixtures with the same field numbers the importer reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from codecortex.precision.schema import (
    DocumentField,
    IndexField,
    MetadataField,
    MultiLineRangeField,
    OccurrenceField,
    PositionEncoding,
    RelationshipField,
    SingleLineRangeField,
    SymbolInformationField,
    SymbolRole,
    ToolInfoField,
)
from codecortex.precision.wire import (
    encode_bytes_field,
    encode_packed_int32_field,
    encode_string_field,
    encode_varint_field,
)


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One occurrence expressed with zero-based positions, as the schema requires."""

    symbol: str
    line: int
    start_column: int
    end_column: int
    roles: int = 0
    end_line: int | None = None
    typed_range: bool = True

    def encode(self) -> bytes:
        payload = encode_string_field(OccurrenceField.SYMBOL, self.symbol)
        if self.roles:
            payload += encode_varint_field(OccurrenceField.SYMBOL_ROLES, self.roles)
        if not self.typed_range:
            values = (
                [self.line, self.start_column, self.end_column]
                if self.end_line is None
                else [self.line, self.start_column, self.end_line, self.end_column]
            )
            return payload + encode_packed_int32_field(OccurrenceField.RANGE, values)
        if self.end_line is None or self.end_line == self.line:
            body = (
                encode_varint_field(SingleLineRangeField.LINE, self.line)
                + encode_varint_field(SingleLineRangeField.START_CHARACTER, self.start_column)
                + encode_varint_field(SingleLineRangeField.END_CHARACTER, self.end_column)
            )
            return payload + encode_bytes_field(OccurrenceField.SINGLE_LINE_RANGE, body)
        body = (
            encode_varint_field(MultiLineRangeField.START_LINE, self.line)
            + encode_varint_field(MultiLineRangeField.START_CHARACTER, self.start_column)
            + encode_varint_field(MultiLineRangeField.END_LINE, self.end_line)
            + encode_varint_field(MultiLineRangeField.END_CHARACTER, self.end_column)
        )
        return payload + encode_bytes_field(OccurrenceField.MULTI_LINE_RANGE, body)


@dataclass(frozen=True, slots=True)
class Relationship:
    symbol: str
    is_implementation: bool = False
    is_reference: bool = False
    is_definition: bool = False

    def encode(self) -> bytes:
        payload = encode_string_field(RelationshipField.SYMBOL, self.symbol)
        if self.is_reference:
            payload += encode_varint_field(RelationshipField.IS_REFERENCE, 1)
        if self.is_implementation:
            payload += encode_varint_field(RelationshipField.IS_IMPLEMENTATION, 1)
        if self.is_definition:
            payload += encode_varint_field(RelationshipField.IS_DEFINITION, 1)
        return payload


@dataclass(frozen=True, slots=True)
class SymbolInfo:
    symbol: str
    display_name: str = ""
    documentation: tuple[str, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    enclosing_symbol: str = ""

    def encode(self) -> bytes:
        payload = encode_string_field(SymbolInformationField.SYMBOL, self.symbol)
        for line in self.documentation:
            payload += encode_string_field(SymbolInformationField.DOCUMENTATION, line)
        for relationship in self.relationships:
            payload += encode_bytes_field(
                SymbolInformationField.RELATIONSHIPS, relationship.encode()
            )
        if self.display_name:
            payload += encode_string_field(
                SymbolInformationField.DISPLAY_NAME, self.display_name
            )
        if self.enclosing_symbol:
            payload += encode_string_field(
                SymbolInformationField.ENCLOSING_SYMBOL, self.enclosing_symbol
            )
        return payload


@dataclass(frozen=True, slots=True)
class Document:
    relative_path: str
    language: str = "Python"
    occurrences: tuple[Occurrence, ...] = ()
    symbols: tuple[SymbolInfo, ...] = ()
    text: str = ""
    position_encoding: PositionEncoding = PositionEncoding.UTF32_CODE_UNIT

    def encode(self) -> bytes:
        payload = encode_string_field(DocumentField.RELATIVE_PATH, self.relative_path)
        for occurrence in self.occurrences:
            payload += encode_bytes_field(DocumentField.OCCURRENCES, occurrence.encode())
        for symbol in self.symbols:
            payload += encode_bytes_field(DocumentField.SYMBOLS, symbol.encode())
        payload += encode_string_field(DocumentField.LANGUAGE, self.language)
        if self.text:
            payload += encode_string_field(DocumentField.TEXT, self.text)
        if self.position_encoding is not PositionEncoding.UNSPECIFIED:
            payload += encode_varint_field(
                DocumentField.POSITION_ENCODING, int(self.position_encoding)
            )
        return payload


def column_in(line_text: str, character_column: int, encoding: PositionEncoding) -> int:
    """Return the column a real indexer would emit for a character position.

    Fixtures describe positions the way a human reads them — "the identifier
    starts at character 6" — while an indexer emits an offset in its own code
    units. This does that translation so a fixture cannot accidentally encode
    the very off-by-one the tests exist to catch.
    """
    prefix = line_text[:character_column]
    if encoding is PositionEncoding.UTF8_CODE_UNIT:
        return len(prefix.encode("utf-8"))
    if encoding is PositionEncoding.UTF16_CODE_UNIT:
        return sum(2 if ord(char) > 0xFFFF else 1 for char in prefix)
    return len(prefix)


@dataclass(slots=True)
class IndexBuilder:
    project_root: str = "file:///workspace"
    tool_name: str = "codecortex-test-indexer"
    tool_version: str = "1.0.0"
    protocol_version: int = 0
    documents: list[Document] = field(default_factory=list)
    external_symbols: list[SymbolInfo] = field(default_factory=list)

    def add(self, document: Document) -> IndexBuilder:
        self.documents.append(document)
        return self

    def encode(self) -> bytes:
        tool = encode_string_field(
            ToolInfoField.NAME, self.tool_name
        ) + encode_string_field(ToolInfoField.VERSION, self.tool_version)
        metadata = (
            encode_varint_field(MetadataField.VERSION, self.protocol_version)
            + encode_bytes_field(MetadataField.TOOL_INFO, tool)
            + encode_string_field(MetadataField.PROJECT_ROOT, self.project_root)
        )
        payload = encode_bytes_field(IndexField.METADATA, metadata)
        for document in self.documents:
            payload += encode_bytes_field(IndexField.DOCUMENTS, document.encode())
        for symbol in self.external_symbols:
            payload += encode_bytes_field(IndexField.EXTERNAL_SYMBOLS, symbol.encode())
        return payload


def symbol(package: str, path: str, *, version: str = "1.0.0", manager: str = "pypi") -> str:
    """Build a well-formed symbol identity string."""
    return f"scip-python {manager} {package} {version} {path}"


DEFINITION = int(SymbolRole.DEFINITION)
IMPORT = int(SymbolRole.IMPORT)
