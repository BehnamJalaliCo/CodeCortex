"""Verify CodeCortex precision constants against the pinned upstream schema.

``src/codecortex/precision/schema.py`` is a hand-written transcription of the
published index schema. A transcription error there produces silently wrong
navigation rather than a crash, so every constant is checked here against the
vendored ``scip.proto`` (see ``tests/fixtures/upstream/README.md`` for the pin
and its provenance).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from codecortex.precision.schema import (
    SUPPORTED_PROTOCOL_VERSIONS,
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
    TextEncoding,
    ToolInfoField,
)
from tests.fixtures.proto_schema import UPSTREAM_ROOT, parse_proto

SCHEMA = parse_proto()

#: Every field CodeCortex reads, as (constant holder, proto message, proto field).
FIELD_CASES: tuple[tuple[type, str, str, int], ...] = (
    (IndexField, "Index", "metadata", IndexField.METADATA),
    (IndexField, "Index", "documents", IndexField.DOCUMENTS),
    (IndexField, "Index", "external_symbols", IndexField.EXTERNAL_SYMBOLS),
    (MetadataField, "Metadata", "version", MetadataField.VERSION),
    (MetadataField, "Metadata", "tool_info", MetadataField.TOOL_INFO),
    (MetadataField, "Metadata", "project_root", MetadataField.PROJECT_ROOT),
    (
        MetadataField,
        "Metadata",
        "text_document_encoding",
        MetadataField.TEXT_DOCUMENT_ENCODING,
    ),
    (ToolInfoField, "ToolInfo", "name", ToolInfoField.NAME),
    (ToolInfoField, "ToolInfo", "version", ToolInfoField.VERSION),
    (ToolInfoField, "ToolInfo", "arguments", ToolInfoField.ARGUMENTS),
    (DocumentField, "Document", "relative_path", DocumentField.RELATIVE_PATH),
    (DocumentField, "Document", "occurrences", DocumentField.OCCURRENCES),
    (DocumentField, "Document", "symbols", DocumentField.SYMBOLS),
    (DocumentField, "Document", "language", DocumentField.LANGUAGE),
    (DocumentField, "Document", "text", DocumentField.TEXT),
    (DocumentField, "Document", "position_encoding", DocumentField.POSITION_ENCODING),
    (OccurrenceField, "Occurrence", "range", OccurrenceField.RANGE),
    (OccurrenceField, "Occurrence", "symbol", OccurrenceField.SYMBOL),
    (OccurrenceField, "Occurrence", "symbol_roles", OccurrenceField.SYMBOL_ROLES),
    (
        OccurrenceField,
        "Occurrence",
        "override_documentation",
        OccurrenceField.OVERRIDE_DOCUMENTATION,
    ),
    (OccurrenceField, "Occurrence", "syntax_kind", OccurrenceField.SYNTAX_KIND),
    (OccurrenceField, "Occurrence", "diagnostics", OccurrenceField.DIAGNOSTICS),
    (OccurrenceField, "Occurrence", "enclosing_range", OccurrenceField.ENCLOSING_RANGE),
    (
        OccurrenceField,
        "Occurrence",
        "single_line_range",
        OccurrenceField.SINGLE_LINE_RANGE,
    ),
    (
        OccurrenceField,
        "Occurrence",
        "multi_line_range",
        OccurrenceField.MULTI_LINE_RANGE,
    ),
    (
        OccurrenceField,
        "Occurrence",
        "single_line_enclosing_range",
        OccurrenceField.SINGLE_LINE_ENCLOSING_RANGE,
    ),
    (
        OccurrenceField,
        "Occurrence",
        "multi_line_enclosing_range",
        OccurrenceField.MULTI_LINE_ENCLOSING_RANGE,
    ),
    (SingleLineRangeField, "SingleLineRange", "line", SingleLineRangeField.LINE),
    (
        SingleLineRangeField,
        "SingleLineRange",
        "start_character",
        SingleLineRangeField.START_CHARACTER,
    ),
    (
        SingleLineRangeField,
        "SingleLineRange",
        "end_character",
        SingleLineRangeField.END_CHARACTER,
    ),
    (
        MultiLineRangeField,
        "MultiLineRange",
        "start_line",
        MultiLineRangeField.START_LINE,
    ),
    (
        MultiLineRangeField,
        "MultiLineRange",
        "start_character",
        MultiLineRangeField.START_CHARACTER,
    ),
    (MultiLineRangeField, "MultiLineRange", "end_line", MultiLineRangeField.END_LINE),
    (
        MultiLineRangeField,
        "MultiLineRange",
        "end_character",
        MultiLineRangeField.END_CHARACTER,
    ),
    (SymbolInformationField, "SymbolInformation", "symbol", SymbolInformationField.SYMBOL),
    (
        SymbolInformationField,
        "SymbolInformation",
        "documentation",
        SymbolInformationField.DOCUMENTATION,
    ),
    (
        SymbolInformationField,
        "SymbolInformation",
        "relationships",
        SymbolInformationField.RELATIONSHIPS,
    ),
    (SymbolInformationField, "SymbolInformation", "kind", SymbolInformationField.KIND),
    (
        SymbolInformationField,
        "SymbolInformation",
        "display_name",
        SymbolInformationField.DISPLAY_NAME,
    ),
    (
        SymbolInformationField,
        "SymbolInformation",
        "signature_documentation",
        SymbolInformationField.SIGNATURE_DOCUMENTATION,
    ),
    (
        SymbolInformationField,
        "SymbolInformation",
        "enclosing_symbol",
        SymbolInformationField.ENCLOSING_SYMBOL,
    ),
    (RelationshipField, "Relationship", "symbol", RelationshipField.SYMBOL),
    (RelationshipField, "Relationship", "is_reference", RelationshipField.IS_REFERENCE),
    (
        RelationshipField,
        "Relationship",
        "is_implementation",
        RelationshipField.IS_IMPLEMENTATION,
    ),
    (
        RelationshipField,
        "Relationship",
        "is_type_definition",
        RelationshipField.IS_TYPE_DEFINITION,
    ),
    (RelationshipField, "Relationship", "is_definition", RelationshipField.IS_DEFINITION),
)


@pytest.mark.parametrize(
    ("message", "proto_field", "constant"),
    [(case[1], case[2], case[3]) for case in FIELD_CASES],
    ids=[f"{case[1]}.{case[2]}" for case in FIELD_CASES],
)
def test_field_numbers_match_the_pinned_schema(
    message: str, proto_field: str, constant: int
) -> None:
    assert SCHEMA.field_number(message, proto_field) == constant


ROLE_CASES: tuple[tuple[str, SymbolRole], ...] = (
    ("Definition", SymbolRole.DEFINITION),
    ("Import", SymbolRole.IMPORT),
    ("WriteAccess", SymbolRole.WRITE_ACCESS),
    ("ReadAccess", SymbolRole.READ_ACCESS),
    ("Generated", SymbolRole.GENERATED),
    ("Test", SymbolRole.TEST),
    ("ForwardDefinition", SymbolRole.FORWARD_DEFINITION),
)


@pytest.mark.parametrize(("proto_name", "flag"), ROLE_CASES, ids=[c[0] for c in ROLE_CASES])
def test_symbol_role_bits_match_the_pinned_schema(proto_name: str, flag: SymbolRole) -> None:
    assert SCHEMA.enum_value("SymbolRole", proto_name) == int(flag)


def test_every_upstream_symbol_role_is_modelled() -> None:
    """A new upstream role must not be silently dropped from role reporting."""
    upstream = {
        name
        for name, value in SCHEMA.enums["SymbolRole"].items()
        if value != 0  # the Unspecified placeholder is not a real role
    }
    modelled = {name.title().replace("_", "") for name in SymbolRole.__members__}
    assert upstream == modelled


POSITION_ENCODING_CASES: tuple[tuple[str, PositionEncoding], ...] = (
    ("UnspecifiedPositionEncoding", PositionEncoding.UNSPECIFIED),
    ("UTF8CodeUnitOffsetFromLineStart", PositionEncoding.UTF8_CODE_UNIT),
    ("UTF16CodeUnitOffsetFromLineStart", PositionEncoding.UTF16_CODE_UNIT),
    ("UTF32CodeUnitOffsetFromLineStart", PositionEncoding.UTF32_CODE_UNIT),
)


@pytest.mark.parametrize(
    ("proto_name", "value"),
    POSITION_ENCODING_CASES,
    ids=[c[0] for c in POSITION_ENCODING_CASES],
)
def test_position_encoding_values_match_the_pinned_schema(
    proto_name: str, value: PositionEncoding
) -> None:
    assert SCHEMA.enum_value("PositionEncoding", proto_name) == int(value)


def test_every_upstream_position_encoding_is_modelled() -> None:
    assert len(SCHEMA.enums["PositionEncoding"]) == len(PositionEncoding)


def test_text_encoding_values_match_the_pinned_schema() -> None:
    assert SCHEMA.enum_value("TextEncoding", "UnspecifiedTextEncoding") == TextEncoding.UNSPECIFIED
    assert SCHEMA.enum_value("TextEncoding", "UTF8") == TextEncoding.UTF8
    assert SCHEMA.enum_value("TextEncoding", "UTF16") == TextEncoding.UTF16


def test_supported_protocol_versions_exist_upstream() -> None:
    upstream = set(SCHEMA.enums["ProtocolVersion"].values())
    assert SUPPORTED_PROTOCOL_VERSIONS <= upstream


def test_schema_documents_half_open_ranges() -> None:
    """The half-open contract is load-bearing for ``SourceRange.contains``."""
    text = (UPSTREAM_ROOT / "scip.proto").read_text(encoding="utf-8")
    assert "half-open [start, end) range within a single line" in text
    assert "half-open [start, end) range spanning multiple lines" in text


def test_vendored_schema_matches_its_provenance_manifest() -> None:
    """The committed fixture must be the exact bytes the manifest claims."""
    manifest = json.loads((UPSTREAM_ROOT / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert manifest["upstream_commit"] == "1c2b6db7e560d5233c944f36e4ac1377cc6963fc"
    assert manifest["modifications"] == "none - vendored byte-identical"
    repo_root = Path(__file__).resolve().parent.parent
    for entry in manifest["files"]:
        payload = (repo_root / entry["local_path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"], entry["local_path"]
        assert len(payload) == entry["bytes"], entry["local_path"]
