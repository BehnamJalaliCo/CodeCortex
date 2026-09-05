"""Optional Tree-sitter parser provider for production polyglot structure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NativeUnit:
    name: str
    kind: str
    line: int
    end_line: int
    signature: str | None = None
    return_type: str | None = None
    bases: tuple[str, ...] = ()
    references: tuple[str, ...] = ()


class TreeSitterParserProvider:
    """Parse major languages with native grammars when the parser extra is installed."""

    aliases = {
        "typescript": "typescript",
        "javascript": "javascript",
        "go": "go",
        "rust": "rust",
        "java": "java",
        "c": "c",
        "cpp": "cpp",
        "csharp": "csharp",
        "php": "php",
        "ruby": "ruby",
    }

    kinds = {
        "class_declaration": "class",
        "class_definition": "class",
        "class_specifier": "class",
        "interface_declaration": "interface",
        "trait_item": "interface",
        "struct_item": "struct",
        "struct_specifier": "struct",
        "enum_item": "enum",
        "enum_declaration": "enum",
        "function_declaration": "function",
        "function_definition": "function",
        "function_item": "function",
        "method_declaration": "method",
        "method_definition": "method",
        "constructor_declaration": "constructor",
        "singleton_method": "method",
    }

    def __init__(self) -> None:
        try:
            from tree_sitter_language_pack import get_parser
        except ImportError as exc:
            raise RuntimeError("install CodeCortex with the `parsers` extra") from exc
        self._get_parser = get_parser
        # One parser per language, kept for the provider's lifetime. `get_parser`
        # builds a fresh Parser (and Language) on every call, so parsing a
        # repository used to construct and drop thousands of native objects.
        self._parsers: dict[str, Any] = {}

    def _parser(self, alias: str) -> Any:
        # Tolerates instances built without __init__ (the unit tests inject a
        # fake `_get_parser` that way).
        parsers = getattr(self, "_parsers", None)
        if parsers is None:
            parsers = {}
            self._parsers = parsers
        parser = parsers.get(alias)
        if parser is None:
            parser = self._get_parser(alias)
            parsers[alias] = parser
        return parser

    @classmethod
    def available(cls) -> bool:
        try:
            import tree_sitter_language_pack  # noqa: F401
        except ImportError:
            return False
        return True

    def parse(self, language: str, source: str) -> list[NativeUnit]:
        alias = self.aliases.get(language)
        if alias is None:
            return []
        parser = self._parser(alias)
        source_bytes = source.encode("utf-8")
        tree = parser.parse(source_bytes)
        root = tree.root_node
        units: list[NativeUnit] = []
        stack = [root]
        while stack:
            node = stack.pop()
            stack.extend(reversed(list(getattr(node, "children", ()))))
            kind = self.kinds.get(str(getattr(node, "type", "")))
            if kind is None:
                continue
            name_node = self._field(node, "name") or self._first_identifier(node)
            if name_node is None:
                continue
            name = self._text(name_node, source_bytes).strip()
            if not name:
                continue
            return_node = self._field(node, "return_type") or self._field(node, "type")
            bases = self._bases(node, source_bytes)
            refs = self._references(node, source_bytes, name)
            units.append(
                NativeUnit(
                    name=name,
                    kind=kind,
                    line=int(node.start_point.row) + 1,
                    end_line=int(node.end_point.row) + 1,
                    signature=self._signature(node, source_bytes),
                    return_type=(
                        self._text(return_node, source_bytes).strip()
                        if return_node is not None
                        else None
                    ),
                    bases=bases,
                    references=refs,
                )
            )
        units.sort(key=lambda item: (item.line, item.end_line, item.name))
        return units

    @staticmethod
    def _field(node: Any, name: str) -> Any | None:
        method = getattr(node, "child_by_field_name", None)
        return method(name) if callable(method) else None

    @staticmethod
    def _text(node: Any, source: bytes) -> str:
        return source[int(node.start_byte) : int(node.end_byte)].decode("utf-8", errors="replace")

    def _first_identifier(self, node: Any) -> Any | None:
        stack = list(getattr(node, "children", ()))
        while stack:
            child = stack.pop(0)
            if str(getattr(child, "type", "")) in {
                "identifier",
                "type_identifier",
                "constant",
                "name",
            }:
                return child
            stack[0:0] = list(getattr(child, "children", ()))
        return None

    def _signature(self, node: Any, source: bytes) -> str | None:
        body = self._field(node, "body")
        end = int(body.start_byte) if body is not None else int(node.end_byte)
        text = source[int(node.start_byte) : end].decode("utf-8", errors="replace").strip()
        text = " ".join(text.split())
        return text[:800] or None

    def _bases(self, node: Any, source: bytes) -> tuple[str, ...]:
        values: list[str] = []
        for field in ("superclass", "interfaces", "base", "type_parameters"):
            child = self._field(node, field)
            if child is not None:
                value = self._text(child, source).strip()
                if value:
                    values.append(value)
        return tuple(dict.fromkeys(values))

    def _references(self, node: Any, source: bytes, own_name: str) -> tuple[str, ...]:
        values: list[str] = []
        stack = list(getattr(node, "children", ()))
        while stack and len(values) < 128:
            child = stack.pop()
            child_type = str(getattr(child, "type", ""))
            if child_type in {"identifier", "type_identifier", "constant"}:
                value = self._text(child, source).strip()
                if value and value != own_name and value not in values:
                    values.append(value)
            stack.extend(getattr(child, "children", ()))
        return tuple(values)
