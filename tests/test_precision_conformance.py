"""CodeCortex-owned precision wire-contract invariants."""

from __future__ import annotations

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


def _values(holder: type) -> list[int]:
    return [
        value
        for name, value in vars(holder).items()
        if name.isupper() and isinstance(value, int)
    ]


def test_wire_field_numbers_are_positive_and_unique_per_message() -> None:
    for holder in (
        IndexField,
        MetadataField,
        ToolInfoField,
        DocumentField,
        OccurrenceField,
        SingleLineRangeField,
        MultiLineRangeField,
        SymbolInformationField,
        RelationshipField,
    ):
        values = _values(holder)
        assert values
        assert all(value > 0 for value in values)
        assert len(values) == len(set(values))


def test_symbol_role_flags_are_independent_bits() -> None:
    values = [int(value) for value in SymbolRole]
    assert values
    assert len(values) == len(set(values))
    assert all(value > 0 and value & (value - 1) == 0 for value in values)


def test_position_encodings_are_stable() -> None:
    assert PositionEncoding.UNSPECIFIED == 0
    assert PositionEncoding.UTF8_CODE_UNIT == 1
    assert PositionEncoding.UTF16_CODE_UNIT == 2
    assert PositionEncoding.UTF32_CODE_UNIT == 3


def test_text_encodings_are_stable() -> None:
    assert TextEncoding.UNSPECIFIED == 0
    assert TextEncoding.UTF8 == 1
    assert TextEncoding.UTF16 == 2


def test_supported_protocol_versions_are_explicit() -> None:
    assert SUPPORTED_PROTOCOL_VERSIONS == frozenset({0})
