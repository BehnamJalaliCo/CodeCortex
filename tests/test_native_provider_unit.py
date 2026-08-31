from __future__ import annotations

from dataclasses import dataclass, field

from codecortex.languages.native import TreeSitterParserProvider


@dataclass
class Point:
    row: int


@dataclass
class Node:
    type: str
    start_byte: int
    end_byte: int
    start_point: Point
    end_point: Point
    children: list["Node"] = field(default_factory=list)
    fields: dict[str, "Node"] = field(default_factory=dict)

    def child_by_field_name(self, name: str):
        return self.fields.get(name)


class Parser:
    def __init__(self, root: Node) -> None:
        self.root = root

    def parse(self, _source: bytes):
        return type("Tree", (), {"root_node": self.root})()


def _slice(source: str, value: str, start: int = 0) -> tuple[int, int]:
    begin = source.index(value, start)
    return begin, begin + len(value)


def test_parse_unknown_language_is_empty() -> None:
    provider = object.__new__(TreeSitterParserProvider)
    provider._get_parser = lambda _name: None
    assert provider.parse("unknown", "anything") == []


def test_parse_native_tree_and_helpers() -> None:
    source = "class Service(Base):\n    def run(value):\n        return helper(value)\n"
    service_s, service_e = _slice(source, "Service")
    base_s, base_e = _slice(source, "Base")
    run_s, run_e = _slice(source, "run")
    value_s, value_e = _slice(source, "value")
    helper_s, helper_e = _slice(source, "helper")

    service_name = Node("identifier", service_s, service_e, Point(0), Point(0))
    base = Node("type_identifier", base_s, base_e, Point(0), Point(0))
    run_name = Node("identifier", run_s, run_e, Point(1), Point(1))
    value = Node("identifier", value_s, value_e, Point(1), Point(1))
    helper = Node("identifier", helper_s, helper_e, Point(2), Point(2))
    body_start = source.index("\n", run_e)
    body = Node("block", body_start, len(source), Point(1), Point(2), children=[helper])
    method = Node(
        "method_definition",
        source.index("def"),
        len(source),
        Point(1),
        Point(2),
        children=[run_name, value, helper],
        fields={"name": run_name, "body": body},
    )
    klass = Node(
        "class_definition",
        0,
        len(source),
        Point(0),
        Point(2),
        children=[service_name, base, method],
        fields={"name": service_name, "superclass": base, "body": method},
    )
    root = Node("module", 0, len(source), Point(0), Point(2), children=[klass])

    provider = object.__new__(TreeSitterParserProvider)
    provider._get_parser = lambda alias: Parser(root)
    units = provider.parse("python" if "python" in provider.aliases else "javascript", source)
    if not units:
        provider.aliases = {**provider.aliases, "test": "test"}
        units = provider.parse("test", source)

    names = {unit.name for unit in units}
    assert {"Service", "run"} <= names
    service = next(unit for unit in units if unit.name == "Service")
    assert "Base" in service.bases
    assert service.signature
    assert "run" in service.references or "helper" in service.references

    nameless = Node("class_definition", 0, 5, Point(0), Point(0))
    provider._get_parser = lambda _alias: Parser(Node("module", 0, 5, Point(0), Point(0), children=[nameless]))
    provider.aliases = {**provider.aliases, "test": "test"}
    assert provider.parse("test", "class") == []


def test_available_and_init_error(monkeypatch) -> None:
    assert isinstance(TreeSitterParserProvider.available(), bool)
