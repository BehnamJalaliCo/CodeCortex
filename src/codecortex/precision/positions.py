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

#: Encodings whose code units are code points, so no conversion is needed. An
#: index that declared nothing is resolved to a concrete encoding before it
#: reaches here (see :mod:`codecortex.precision.compatibility`), so UNSPECIFIED
#: is included only as a defensive identity case.
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


def protocol_to_character(
    line_text: str, column: int, encoding: PositionEncoding
) -> ColumnConversion:
    """Convert an indexer column into a zero-based Python character column."""
    if column <= 0:
        return ColumnConversion(0)
    if encoding in _IDENTITY_ENCODINGS:
        return ColumnConversion(column)

    offsets = _code_unit_offsets(line_text, encoding)
    total = offsets[-1]
    if column >= total:
        # A column at or past the end of the line: keep the overshoot so that
        # an end-exclusive boundary one past the last character stays one past.
        return ColumnConversion(len(line_text) + (column - total))

    # Walk to the character whose code units cover the requested offset.
    for index in range(len(offsets) - 1):
        if offsets[index] == column:
            return ColumnConversion(index)
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
    return ColumnConversion(len(line_text))  # pragma: no cover - guarded above


def character_to_protocol(
    line_text: str, column: int, encoding: PositionEncoding
) -> ColumnConversion:
    """Convert a zero-based Python character column into an indexer column."""
    if column <= 0:
        return ColumnConversion(0)
    if encoding in _IDENTITY_ENCODINGS:
        return ColumnConversion(column)

    offsets = _code_unit_offsets(line_text, encoding)
    if column < len(offsets):
        return ColumnConversion(offsets[column])
    return ColumnConversion(offsets[-1] + (column - len(line_text)))


def encoding_is_undecidable(line_text: str, character_column: int) -> bool:
    """Whether the encoding matters for a position on this line.

    Every encoding agrees on an ASCII prefix, so an unverified assumption about
    which unit an index used is harmless there and unsound after the first
    non-ASCII character.
    """
    return not line_text[: max(0, character_column)].isascii()
