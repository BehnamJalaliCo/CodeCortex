"""Parser for the standardized symbol-identity string used by precision indexes.

The published grammar is::

    <symbol>    ::= <scheme> ' ' <package> ' ' (<descriptor>)+ | 'local ' <local-id>
    <package>   ::= <manager> ' ' <package-name> ' ' <version>

Spaces inside a field are escaped by doubling them, and identifiers containing
non-identifier characters are wrapped in backticks (a literal backtick is
doubled). Descriptor suffixes encode what kind of entity each path segment is.

Symbol names alone are not a safe identity: two packages can export the same
name, and the same name can appear at several nesting levels. Parsing the full
identity lets CodeCortex distinguish them without relying on the name.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DescriptorKind(StrEnum):
    NAMESPACE = "namespace"
    TYPE = "type"
    TERM = "term"
    META = "meta"
    MACRO = "macro"
    METHOD = "method"
    TYPE_PARAMETER = "type_parameter"
    PARAMETER = "parameter"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Descriptor:
    name: str
    kind: DescriptorKind
    disambiguator: str = ""


@dataclass(frozen=True, slots=True)
class SymbolIdentity:
    """Decomposed symbol identity that never depends on the display name alone."""

    raw: str
    scheme: str = ""
    manager: str = ""
    package_name: str = ""
    package_version: str = ""
    descriptors: tuple[Descriptor, ...] = ()
    is_local: bool = False
    parse_error: str = ""

    @property
    def display_name(self) -> str:
        if self.descriptors:
            return self.descriptors[-1].name
        return self.raw

    @property
    def container(self) -> str:
        """Dotted owner path excluding the leaf descriptor."""
        return ".".join(item.name for item in self.descriptors[:-1])

    @property
    def qualified_name(self) -> str:
        return ".".join(item.name for item in self.descriptors)

    @property
    def kind(self) -> DescriptorKind:
        return self.descriptors[-1].kind if self.descriptors else DescriptorKind.UNKNOWN

    @property
    def is_callable(self) -> bool:
        return self.kind is DescriptorKind.METHOD

    @property
    def is_type(self) -> bool:
        return self.kind is DescriptorKind.TYPE

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.raw,
            "scheme": self.scheme,
            "package_manager": self.manager,
            "package_name": self.package_name,
            "package_version": self.package_version,
            "qualified_name": self.qualified_name,
            "display_name": self.display_name,
            "container": self.container,
            "kind": self.kind.value,
            "local": self.is_local,
        }


def _split_escaped_spaces(value: str, parts: int) -> tuple[list[str], str]:
    """Split ``value`` into ``parts`` space-separated fields, honouring doubled spaces."""
    fields: list[str] = []
    current: list[str] = []
    index = 0
    length = len(value)
    while index < length and len(fields) < parts:
        char = value[index]
        if char != " ":
            current.append(char)
            index += 1
            continue
        if index + 1 < length and value[index + 1] == " ":
            current.append(" ")
            index += 2
            continue
        fields.append("".join(current))
        current = []
        index += 1
    if len(fields) < parts:
        fields.append("".join(current))
        index = length
    return fields, value[index:]


def _read_identifier(value: str, start: int) -> tuple[str, int]:
    """Read a simple or backtick-escaped identifier starting at ``start``."""
    if start < len(value) and value[start] == "`":
        index = start + 1
        out: list[str] = []
        while index < len(value):
            if value[index] == "`":
                if index + 1 < len(value) and value[index + 1] == "`":
                    out.append("`")
                    index += 2
                    continue
                return "".join(out), index + 1
            out.append(value[index])
            index += 1
        raise ValueError("unterminated escaped identifier")
    index = start
    while index < len(value) and (value[index].isalnum() or value[index] in "_+-$"):
        index += 1
    if index == start:
        raise ValueError(f"expected an identifier at offset {start}")
    return value[start:index], index


_SUFFIXES: dict[str, DescriptorKind] = {
    "/": DescriptorKind.NAMESPACE,
    "#": DescriptorKind.TYPE,
    ".": DescriptorKind.TERM,
    ":": DescriptorKind.META,
    "!": DescriptorKind.MACRO,
}


def parse_descriptors(value: str) -> tuple[Descriptor, ...]:
    """Parse the descriptor suffix of a symbol identity string."""
    descriptors: list[Descriptor] = []
    index = 0
    length = len(value)
    while index < length:
        char = value[index]
        if char == "[":
            name, index = _read_identifier(value, index + 1)
            if index >= length or value[index] != "]":
                raise ValueError("unterminated type parameter descriptor")
            descriptors.append(Descriptor(name, DescriptorKind.TYPE_PARAMETER))
            index += 1
            continue
        if char == "(":
            name, index = _read_identifier(value, index + 1)
            if index >= length or value[index] != ")":
                raise ValueError("unterminated parameter descriptor")
            descriptors.append(Descriptor(name, DescriptorKind.PARAMETER))
            index += 1
            continue
        name, index = _read_identifier(value, index)
        if index < length and value[index] == "(":
            close = value.find(").", index)
            if close == -1:
                raise ValueError("unterminated method descriptor")
            descriptors.append(
                Descriptor(name, DescriptorKind.METHOD, value[index + 1 : close])
            )
            index = close + 2
            continue
        if index >= length:
            raise ValueError("descriptor is missing its suffix")
        suffix = _SUFFIXES.get(value[index])
        if suffix is None:
            raise ValueError(f"unknown descriptor suffix: {value[index]!r}")
        descriptors.append(Descriptor(name, suffix))
        index += 1
    if not descriptors:
        raise ValueError("symbol identity has no descriptors")
    return tuple(descriptors)


def parse_symbol(value: str) -> SymbolIdentity:
    """Parse a symbol identity string, degrading gracefully on unknown shapes.

    A symbol that does not conform to the grammar is still returned with its raw
    text and a ``parse_error``: navigation must never crash on an index produced
    by a tool that emits a dialect this parser has not seen.
    """
    if not value:
        return SymbolIdentity(raw=value, parse_error="empty symbol")
    if value.startswith("local "):
        return SymbolIdentity(
            raw=value,
            scheme="local",
            descriptors=(Descriptor(value[6:], DescriptorKind.TERM),),
            is_local=True,
        )
    fields, remainder = _split_escaped_spaces(value, 4)
    if len(fields) < 4 or not remainder:
        return SymbolIdentity(raw=value, parse_error="symbol is missing required fields")
    scheme, manager, package_name, package_version = fields
    try:
        descriptors = parse_descriptors(remainder)
    except ValueError as exc:
        return SymbolIdentity(
            raw=value,
            scheme=scheme,
            manager="" if manager == "." else manager,
            package_name="" if package_name == "." else package_name,
            package_version="" if package_version == "." else package_version,
            parse_error=str(exc),
        )
    return SymbolIdentity(
        raw=value,
        scheme=scheme,
        manager="" if manager == "." else manager,
        package_name="" if package_name == "." else package_name,
        package_version="" if package_version == "." else package_version,
        descriptors=descriptors,
    )
