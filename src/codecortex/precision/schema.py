"""Field numbers and role flags transcribed from the published index schema.

Keeping the schema constants in one place makes the importer auditable against
the upstream ``.proto`` definition recorded in ``docs/provenance/precision-intelligence.md``.
Only the fields CodeCortex actually consumes are listed.
"""

from __future__ import annotations

from enum import IntFlag


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
    ENCLOSING_RANGE = 7
    SINGLE_LINE_RANGE = 8
    MULTI_LINE_RANGE = 9


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


#: Schema protocol versions this importer has been validated against.
SUPPORTED_PROTOCOL_VERSIONS = frozenset({0})
