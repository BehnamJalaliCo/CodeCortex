"""Minimal ``.proto`` reader used to verify CodeCortex schema constants.

This is deliberately not a general protobuf parser. It extracts exactly what a
conformance test needs from the pinned upstream schema: for each top-level
message, the field name to field number mapping (including fields declared
inside a ``oneof``), and for each enum, the value name to number mapping.

Parsing the real schema is what makes the constants in
``codecortex.precision.schema`` auditable: a transcription error, or an
upstream renumbering after a pin move, fails a test instead of silently
producing wrong navigation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

UPSTREAM_ROOT = Path(__file__).resolve().parent / "upstream" / "scip"
SCIP_PROTO = UPSTREAM_ROOT / "scip.proto"

_COMMENT = re.compile(r"//.*$")
_BLOCK_OPEN = re.compile(r"^(message|enum|oneof)\s+(\w+)\s*\{")
# `repeated int32 range = 1 [deprecated = true];` and friends.
_FIELD = re.compile(
    r"^(?:optional\s+|repeated\s+)?[\w.<>, ]+?\s+(\w+)\s*=\s*(\d+)\s*(?:\[[^\]]*\])?\s*;"
)
# `Definition = 0x1;` / `UTF8 = 1;` / `AbstractMethod = 66;`
_ENUM_VALUE = re.compile(r"^(\w+)\s*=\s*(0x[0-9a-fA-F]+|\d+)\s*(?:\[[^\]]*\])?\s*;")


@dataclass(frozen=True, slots=True)
class ProtoSchema:
    """Field and enum numbering extracted from one ``.proto`` file."""

    messages: dict[str, dict[str, int]] = field(default_factory=dict)
    enums: dict[str, dict[str, int]] = field(default_factory=dict)

    def field_number(self, message: str, name: str) -> int:
        return self.messages[message][name]

    def enum_value(self, enum: str, name: str) -> int:
        return self.enums[enum][name]


def parse_proto(path: Path = SCIP_PROTO) -> ProtoSchema:
    """Parse the message and enum numbering out of a ``.proto`` source file."""
    messages: dict[str, dict[str, int]] = {}
    enums: dict[str, dict[str, int]] = {}
    # Stack of (kind, name). A `oneof` does not introduce a namespace: its
    # fields belong to the enclosing message, so it is pushed but not named.
    stack: list[tuple[str, str]] = []

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = _COMMENT.sub("", raw).strip()
        if not line:
            continue
        opened = _BLOCK_OPEN.match(line)
        if opened is not None:
            kind, name = opened.group(1), opened.group(2)
            if kind == "message":
                messages.setdefault(name, {})
            elif kind == "enum":
                enums.setdefault(name, {})
            stack.append((kind, name))
            continue
        if line.startswith("}"):
            if stack:
                stack.pop()
            continue
        if not stack:
            continue

        owner_kind, owner_name = _owner(stack)
        if owner_kind == "enum":
            match = _ENUM_VALUE.match(line)
            if match is not None:
                enums[owner_name][match.group(1)] = int(match.group(2), 0)
            continue
        match = _FIELD.match(line)
        if match is not None:
            messages[owner_name][match.group(1)] = int(match.group(2))

    return ProtoSchema(messages=messages, enums=enums)


def _owner(stack: list[tuple[str, str]]) -> tuple[str, str]:
    """Return the innermost block that owns declarations, skipping ``oneof``."""
    for kind, name in reversed(stack):
        if kind != "oneof":
            return kind, name
    return stack[-1]
