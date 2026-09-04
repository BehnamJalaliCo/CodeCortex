"""Minimal, dependency-free reader for the binary index encoding.

CodeCortex consumes an existing precision index rather than inventing a
competing code-index protocol. The index is distributed in the standard
protocol-buffer binary encoding, so this module implements exactly the subset
of that wire format the importer needs: varints, length-delimited submessages,
packed and unpacked repeated scalars, and skipping of unknown fields.

This is a structured decoder driven by the published schema field numbers in
``codecortex.precision.schema`` — never a regular expression over serialized
bytes. Every malformed input raises :class:`WireFormatError` so the importer
can fall back cleanly instead of producing wrong navigation results.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VARINT = 0
FIXED64 = 1
LENGTH_DELIMITED = 2
START_GROUP = 3
END_GROUP = 4
FIXED32 = 5

#: Protocol buffers cap varints at 10 bytes for a 64-bit value.
_MAX_VARINT_BYTES = 10


class WireFormatError(ValueError):
    """Raised when the byte stream does not conform to the binary encoding."""


def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Decode one base-128 varint, returning ``(value, next_offset)``."""
    result = 0
    shift = 0
    consumed = 0
    length = len(data)
    while True:
        if offset >= length:
            raise WireFormatError("truncated varint")
        if consumed >= _MAX_VARINT_BYTES:
            raise WireFormatError("varint exceeds 64 bits")
        byte = data[offset]
        result |= (byte & 0x7F) << shift
        offset += 1
        consumed += 1
        if not byte & 0x80:
            return result, offset
        shift += 7


@dataclass(slots=True)
class Message:
    """Decoded fields of one message, grouped by field number.

    Values are stored as ``int`` for varint/fixed fields and ``bytes`` for
    length-delimited fields, preserving repetition order.
    """

    fields: dict[int, list[int | bytes]] = field(default_factory=dict)

    def _values(self, number: int) -> list[int | bytes]:
        return self.fields.get(number, [])

    def scalar(self, number: int, default: int = 0) -> int:
        """Return the last varint value for ``number`` (proto3 last-wins)."""
        values = [value for value in self._values(number) if isinstance(value, int)]
        return values[-1] if values else default

    def has(self, number: int) -> bool:
        return bool(self._values(number))

    def raw(self, number: int) -> bytes | None:
        values = [value for value in self._values(number) if isinstance(value, bytes)]
        return values[-1] if values else None

    def text(self, number: int, default: str = "") -> str:
        """Return the last length-delimited value decoded as UTF-8."""
        payload = self.raw(number)
        if payload is None:
            return default
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WireFormatError(f"field {number} is not valid UTF-8") from exc

    def texts(self, number: int) -> list[str]:
        result: list[str] = []
        for value in self._values(number):
            if not isinstance(value, bytes):
                continue
            try:
                result.append(value.decode("utf-8"))
            except UnicodeDecodeError as exc:
                raise WireFormatError(f"field {number} is not valid UTF-8") from exc
        return result

    def message(self, number: int, *, max_depth: int = 32) -> Message | None:
        payload = self.raw(number)
        return None if payload is None else decode_message(payload, max_depth=max_depth)

    def messages(self, number: int, *, max_depth: int = 32) -> list[Message]:
        return [
            decode_message(value, max_depth=max_depth)
            for value in self._values(number)
            if isinstance(value, bytes)
        ]

    def int32s(self, number: int) -> list[int]:
        """Return a repeated int32 field, accepting both packed and unpacked encodings."""
        result: list[int] = []
        for value in self._values(number):
            if isinstance(value, int):
                result.append(_as_int32(value))
                continue
            offset = 0
            while offset < len(value):
                item, offset = read_varint(value, offset)
                result.append(_as_int32(item))
        return result


def _as_int32(value: int) -> int:
    """Reinterpret a decoded varint as a signed 32-bit protocol integer."""
    value &= 0xFFFFFFFFFFFFFFFF
    if value >= 0x8000000000000000:
        value -= 0x10000000000000000
    return value


def decode_message(data: bytes, *, max_depth: int = 32) -> Message:
    """Decode one message body into field lists, skipping unknown fields."""
    if max_depth <= 0:
        raise WireFormatError("message nesting is too deep")
    message = Message()
    offset = 0
    length = len(data)
    while offset < length:
        key, offset = read_varint(data, offset)
        number = key >> 3
        wire_type = key & 0x07
        if number == 0:
            raise WireFormatError("field number 0 is not valid")
        if wire_type == VARINT:
            value, offset = read_varint(data, offset)
            message.fields.setdefault(number, []).append(value)
        elif wire_type == LENGTH_DELIMITED:
            size, offset = read_varint(data, offset)
            end = offset + size
            if size < 0 or end > length:
                raise WireFormatError("length-delimited field overruns the buffer")
            message.fields.setdefault(number, []).append(data[offset:end])
            offset = end
        elif wire_type == FIXED64:
            if offset + 8 > length:
                raise WireFormatError("truncated 64-bit field")
            message.fields.setdefault(number, []).append(
                int.from_bytes(data[offset : offset + 8], "little")
            )
            offset += 8
        elif wire_type == FIXED32:
            if offset + 4 > length:
                raise WireFormatError("truncated 32-bit field")
            message.fields.setdefault(number, []).append(
                int.from_bytes(data[offset : offset + 4], "little")
            )
            offset += 4
        else:
            raise WireFormatError(f"unsupported wire type: {wire_type}")
    return message


def encode_varint(value: int) -> bytes:
    """Encode an integer as a base-128 varint (negatives are sign-extended to 64 bits)."""
    if value < 0:
        value += 0x10000000000000000
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def encode_varint_field(number: int, value: int) -> bytes:
    return encode_varint((number << 3) | VARINT) + encode_varint(value)


def encode_bytes_field(number: int, payload: bytes) -> bytes:
    return encode_varint((number << 3) | LENGTH_DELIMITED) + encode_varint(len(payload)) + payload


def encode_string_field(number: int, value: str) -> bytes:
    return encode_bytes_field(number, value.encode("utf-8"))


def encode_packed_int32_field(number: int, values: list[int]) -> bytes:
    return encode_bytes_field(number, b"".join(encode_varint(item) for item in values))
