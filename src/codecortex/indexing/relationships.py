"""Extract dependency and call relationships from source files."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Relationship:
    kind: str
    target: str
    line: int
    source_symbol: str | None = None


class RelationshipExtractor:
    _CALL_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")
    _JS_IMPORT_RE = re.compile(
        r"^\s*(?:import\s+(?:[^\n]+?\s+from\s+)?|require\s*\()[\"']([^\"']+)",
        re.MULTILINE,
    )
    _GO_IMPORT_RE = re.compile(r"^\s*import\s+[\"']([^\"']+)[\"']", re.MULTILINE)
    _RUST_USE_RE = re.compile(r"^\s*use\s+([^;]+);", re.MULTILINE)
    _JVM_IMPORT_RE = re.compile(r"^\s*import\s+([A-Za-z_][\w.*]+)\s*;", re.MULTILINE)
    _C_INCLUDE_RE = re.compile(r"^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]", re.MULTILINE)
    _PHP_USE_RE = re.compile(r"^\s*use\s+([^;]+);", re.MULTILINE)
    _RUBY_REQUIRE_RE = re.compile(
        r"^\s*require(?:_relative)?\s+[\"']([^\"']+)[\"']",
        re.MULTILINE,
    )
    _EXTENDS_RE = re.compile(
        r"\bclass\s+([A-Za-z_$]\w*)\s+extends\s+([A-Za-z_$]\w*)",
        re.MULTILINE,
    )
    _IMPLEMENTS_RE = re.compile(
        r"\bclass\s+([A-Za-z_$]\w*)[^\n{]*\bimplements\s+([A-Za-z_$][\w$.,\s]*)",
        re.MULTILINE,
    )
    _CALL_KEYWORDS = {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "return",
        "sizeof",
        "typeof",
        "function",
        "def",
        "class",
        "new",
    }

    def extract(self, path: Path, source: str) -> list[Relationship]:
        if path.suffix.lower() == ".py":
            return self._python(source)
        result = self._imports(path, source)
        result.extend(self._inheritance(source))
        result.extend(self._calls(source))
        return self._dedupe(result)

    @staticmethod
    def _python(source: str) -> list[Relationship]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        result: list[Relationship] = []
        containers: list[str] = []

        class Visitor(ast.NodeVisitor):
            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                for base in node.bases:
                    name = RelationshipExtractor._python_name(base)
                    if name:
                        result.append(Relationship("inherits", name, node.lineno, node.name))
                containers.append(node.name)
                self.generic_visit(node)
                containers.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                containers.append(node.name)
                self.generic_visit(node)
                containers.pop()

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                containers.append(node.name)
                self.generic_visit(node)
                containers.pop()

            def visit_Import(self, node: ast.Import) -> None:
                for alias in node.names:
                    result.append(Relationship("imports", alias.name, node.lineno))

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                if node.module:
                    result.append(Relationship("imports", node.module, node.lineno))

            def visit_Call(self, node: ast.Call) -> None:
                name = RelationshipExtractor._python_name(node.func)
                if name:
                    result.append(
                        Relationship(
                            "calls",
                            name.split(".")[-1],
                            node.lineno,
                            containers[-1] if containers else None,
                        )
                    )
                self.generic_visit(node)

        Visitor().visit(tree)
        return RelationshipExtractor._dedupe(result)

    @staticmethod
    def _python_name(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = RelationshipExtractor._python_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return None

    def _imports(self, path: Path, source: str) -> list[Relationship]:
        suffix = path.suffix.lower()
        pattern: re.Pattern[str] | None = None
        if suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}:
            pattern = self._JS_IMPORT_RE
        elif suffix == ".go":
            pattern = self._GO_IMPORT_RE
        elif suffix == ".rs":
            pattern = self._RUST_USE_RE
        elif suffix in {".java", ".cs"}:
            pattern = self._JVM_IMPORT_RE
        elif suffix in {".c", ".h", ".cc", ".cpp", ".cxx", ".hpp"}:
            pattern = self._C_INCLUDE_RE
        elif suffix == ".php":
            pattern = self._PHP_USE_RE
        elif suffix == ".rb":
            pattern = self._RUBY_REQUIRE_RE
        if pattern is None:
            return []
        return [
            Relationship("imports", match.group(1).strip(), source.count("\n", 0, match.start()) + 1)
            for match in pattern.finditer(source)
        ]

    def _inheritance(self, source: str) -> list[Relationship]:
        result = [
            Relationship("inherits", match.group(2), source.count("\n", 0, match.start()) + 1, match.group(1))
            for match in self._EXTENDS_RE.finditer(source)
        ]
        for match in self._IMPLEMENTS_RE.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            for target in match.group(2).split(","):
                target = target.strip()
                if target:
                    result.append(Relationship("implements", target, line, match.group(1)))
        return result

    def _calls(self, source: str) -> list[Relationship]:
        result: list[Relationship] = []
        for match in self._CALL_RE.finditer(source):
            name = match.group(1)
            if name in self._CALL_KEYWORDS:
                continue
            result.append(Relationship("calls", name, source.count("\n", 0, match.start()) + 1))
        return result

    @staticmethod
    def _dedupe(items: list[Relationship]) -> list[Relationship]:
        seen: set[tuple[str, str, int, str | None]] = set()
        result: list[Relationship] = []
        for item in items:
            key = (item.kind, item.target, item.line, item.source_symbol)
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result
