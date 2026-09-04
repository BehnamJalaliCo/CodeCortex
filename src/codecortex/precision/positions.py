"""Convert between indexer column offsets and Python character columns.

An index does not store character columns. It stores an offset from the start
of the line measured in code units of the encoding the indexer declared in
``Document.position_encoding``, which usually matches whatever its
implementation language indexes strings by:

===============================  ==========================================
Declared encoding                Offset unit
===============================  ==========================================
``UTF8_CODE_UNIT``               bytes (Go, Rust, C++ indexers)
``UTF16_CODE_UNIT``              UTF-16 code units (JVM, .NET, TS/JS)
``UTF32_CODE_UNIT``              code points (Python indexers)
===============================  ==========================================

Python string indices are code points, so only ``UTF32_CODE_UNIT`` can be used
directly. For a line containing ``"🚀 Woo"``, the ``W`` sits at byte offset 5,
UTF-16 offset 3, and code point offset 2 — three different numbers for one
position. Treating any of them as a Python index silently resolves the wrong
symbol, which is worse than failing.

CodeCortex's internal and public convention is code points. Every offset that
crosses the boundary between an index and CodeCortex passes through here.
"""

from __future__ import annotations

from dataclasses import dataclass

from codecortex.precision.schema import PositionEncoding

#: Encodings whose code units are code points, so no conversion is needed.
_IDENTITY_ENCODINGS = frozenset(
    {PositionEncoding.UTF32_CODE_UNIT, PositionEncoding.UNSPECIFIED}
)


@dataclass(frozen=True, slots=True)
class ColumnConversion:
    """A converted column, plus whether the conversion had to guess."""

    column: int
    ambiguous: bool = False
    reason: str = ""


def _code_unit_offsets(line_text: str, encoding: PositionEncoding) -> list[int]:
    """Return the cumulative code-unit offset before each character, plus the total."""
    offsets = [0]
    total = 0
    if encoding is PositionEncoding.UTF8_CODE_UNIT:
        for char in line_text:
            total += len(char.encode("utf-8"))
            offsets.append(total)
    elif encoding is PositionEncoding.UTF16_CODE_UNIT:
        for char in line_text:
            total += 2 if ord(char) > 0xFFFF else 1
            offsets.append(total)
    else:
        for _ in line_text:
            total += 1
            offsets.append(total)
    return offsets


def _unspecified_ambiguity(line_text: str, character_column: int) -> str:
    """Report why an unspecified encoding cannot be trusted on this line.

    The schema says a conforming indexer must not leave the encoding
    unspecified. When one does, every encoding agrees on a pure-ASCII prefix
    and disagrees otherwise, so ambiguity is reported only where it is real.
    """
    prefix = line_text[: max(0, character_column)]
    if prefix.isascii():
        return ""
    return (
        "the index did not declare a position encoding and the line contains "
        "non-ASCII text, so the column could refer to bytes, UTF-16 code units, "
        "or code points"
    )


def protocol_to_character(
    line_text: str, column: int, encoding: PositionEncoding
) -> ColumnConversion:
    """Convert an indexer column into a zero-based Python character column."""
    if column <= 0:
        return ColumnConversion(0)
    if encoding in _IDENTITY_ENCODINGS and line_text.isascii():
        return ColumnConversion(column)

    offsets = _code_unit_offsets(line_text, encoding)
    total = offsets[-1]
    if column >= total:
        # A column at or past the end of the line: keep the overshoot so that
        # an end-exclusive boundary one past the last character stays one past.
        character = len(line_text) + (column - total)
        return _annotate(line_text, character, encoding)

    # Walk to the character whose code units cover the requested offset.
    character = 0
    for index in range(len(offsets) - 1):
        if offsets[index] == column:
            character = index
            break
        if offsets[index] < column < offsets[index + 1]:
            # The offset lands inside a multi-unit character. No character
            # column represents that position, so clamp to the character that
            # contains it and say the conversion was not exact.
            return ColumnConversion(
                index,
                ambiguous=True,
                reason=(
                    f"column {column} falls inside a multi-code-unit character; "
                    f"clamped to the start of that character"
                ),
            )
    else:  # pragma: no cover - the column < total guard makes this unreachable
        character = len(line_text)
    return _annotate(line_text, character, encoding)


def character_to_protocol(
    line_text: str, column: int, encoding: PositionEncoding
) -> ColumnConversion:
    """Convert a zero-based Python character column into an indexer column."""
    if column <= 0:
        return ColumnConversion(0)
    if encoding in _IDENTITY_ENCODINGS and line_text.isascii():
        return ColumnConversion(column)

    offsets = _code_unit_offsets(line_text, encoding)
    if column < len(offsets):
        converted = offsets[column]
    else:
        converted = offsets[-1] + (column - len(line_text))
    ambiguity = (
        _unspecified_ambiguity(line_text, column)
        if encoding is PositionEncoding.UNSPECIFIED
        else ""
    )
    return ColumnConversion(converted, ambiguous=bool(ambiguity), reason=ambiguity)


def _annotate(
    line_text: str, character: int, encoding: PositionEncoding
) -> ColumnConversion:
    if encoding is not PositionEncoding.UNSPECIFIED:
        return ColumnConversion(character)
    ambiguity = _unspecified_ambiguity(line_text, character)
    return ColumnConversion(character, ambiguous=bool(ambiguity), reason=ambiguity)
