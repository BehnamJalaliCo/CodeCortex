"""Wire-field numbers and role flags used by CodeCortex precision indexes.

The importer keeps the compact wire contract in one module so parsing behavior
is explicit, reviewable, and covered by repository-owned conformance tests.
Only fields CodeCortex consumes are listed here.
"""

from __future__ import annotations

from enum import IntEnum, IntFlag


class IndexField:
    METADATA = 1
    DOCUMENTS = 2
    EXTERNAL_SYMBOLS = 3


class MetadataField:
    VERSION = 1
    TOOL_INFO = 2
    PROJECT_ROOT = 3
    TEXT_DOCUMENT_ENCODING = 4


class ToolInfoField:
    NAME = 1
    VERSION = 2
    ARGUMENTS = 3


class DocumentField:
    RELATIVE_PATH = 1
    OCCURRENCES = 2
    SYMBOLS = 3
    LANGUAGE = 4
    TEXT = 5
    POSITION_ENCODING = 6


class OccurrenceField:
    RANGE = 1
    SYMBOL = 2
    SYMBOL_ROLES = 3
    OVERRIDE_DOCUMENTATION = 4
    SYNTAX_KIND = 5
    DIAGNOSTICS = 6
    ENCLOSING_RANGE = 7
    SINGLE_LINE_RANGE = 8
    MULTI_LINE_RANGE = 9
    SINGLE_LINE_ENCLOSING_RANGE = 10
    MULTI_LINE_ENCLOSING_RANGE = 11


class SingleLineRangeField:
    LINE = 1
    START_CHARACTER = 2
    END_CHARACTER = 3


class MultiLineRangeField:
    START_LINE = 1
    START_CHARACTER = 2
    END_LINE = 3
    END_CHARACTER = 4


class SymbolInformationField:
    SYMBOL = 1
    DOCUMENTATION = 3
    RELATIONSHIPS = 4
    KIND = 5
    DISPLAY_NAME = 6
    SIGNATURE_DOCUMENTATION = 7
    ENCLOSING_SYMBOL = 8


class RelationshipField:
    SYMBOL = 1
    IS_REFERENCE = 2
    IS_IMPLEMENTATION = 3
    IS_TYPE_DEFINITION = 4
    IS_DEFINITION = 5


class SymbolRole(IntFlag):
    """Bit flags carried by ``Occurrence.symbol_roles``."""

    DEFINITION = 0x1
    IMPORT = 0x2
    WRITE_ACCESS = 0x4
    READ_ACCESS = 0x8
    GENERATED = 0x10
    TEST = 0x20
    FORWARD_DEFINITION = 0x40


class PositionEncoding(IntEnum):
    """How an indexer expressed occurrence columns, per ``Document.position_encoding``.

    Columns are *not* Python string indices. An indexer reports an offset from
    the start of the line measured in code units of the declared encoding, so a
    line containing any non-ASCII character needs conversion before the offset
    can be used against a Python ``str``.
    """

    UNSPECIFIED = 0
    UTF8_CODE_UNIT = 1
    UTF16_CODE_UNIT = 2
    UTF32_CODE_UNIT = 3


class TextEncoding(IntEnum):
    """How ``Document.text`` was encoded, per ``Metadata.text_document_encoding``."""

    UNSPECIFIED = 0
    UTF8 = 1
    UTF16 = 2


#: Schema protocol versions this importer has been validated against.
SUPPORTED_PROTOCOL_VERSIONS = frozenset({0})
