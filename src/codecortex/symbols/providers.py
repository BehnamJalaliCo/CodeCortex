"""Lightweight multi-language symbol providers."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SymbolRecord:
    name: str
    kind: str
    path: Path
    line: int
    language: str
    container: str | None = None


class SymbolProvider(Protocol):
    language: str
    suffixes: tuple[str, ...]

    def extract(self, path: Path, source: str) -> list[SymbolRecord]: ...


class PythonProvider:
    language = "python"
    suffixes = (".py",)

    def extract(self, path: Path, source: str) -> list[SymbolRecord]:
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            return []
        result: list[SymbolRecord] = []
        parents: dict[ast.AST, str] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                if isinstance(parent, ast.ClassDef):
                    parents[child] = parent.name
                elif parent in parents:
                    parents[child] = parents[parent]
        for node in ast.walk(tree):
            container = parents.get(node)
            if isinstance(node, ast.ClassDef):
                result.append(SymbolRecord(node.name, "class", path, node.lineno, self.language))
            elif isinstance(node, ast.AsyncFunctionDef):
                kind = "method" if container else "async_function"
                result.append(
                    SymbolRecord(node.name, kind, path, node.lineno, self.language, container)
                )
            elif isinstance(node, ast.FunctionDef):
                kind = "method" if container else "function"
                result.append(
                    SymbolRecord(node.name, kind, path, node.lineno, self.language, container)
                )
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif node.module:
                    names = [node.module]
                for name in names:
                    result.append(SymbolRecord(name, "import", path, node.lineno, self.language))
        return result


@dataclass(frozen=True, slots=True)
class Pattern:
    kind: str
    regex: re.Pattern[str]
    group: int = 1


class RegexProvider:
    def __init__(self, language: str, suffixes: tuple[str, ...], patterns: list[Pattern]) -> None:
        self.language = language
        self.suffixes = suffixes
        self.patterns = patterns

    def extract(self, path: Path, source: str) -> list[SymbolRecord]:
        result: list[SymbolRecord] = []
        seen: set[tuple[str, str, int]] = set()
        for pattern in self.patterns:
            for match in pattern.regex.finditer(source):
                name = match.group(pattern.group).strip()
                line = source.count("\n", 0, match.start()) + 1
                key = (name, pattern.kind, line)
                if not name or key in seen:
                    continue
                seen.add(key)
                result.append(SymbolRecord(name, pattern.kind, path, line, self.language))
        return result


def _p(kind: str, expression: str, flags: int = re.MULTILINE) -> Pattern:
    return Pattern(kind, re.compile(expression, flags))


_JS_PATTERNS = [
    _p("class", r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)"),
    _p("interface", r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)"),
    _p("type", r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*="),
    _p("enum", r"^\s*(?:export\s+)?enum\s+([A-Za-z_$][\w$]*)"),
    _p("function", r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"),
    _p("function", r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^\n]*\)\s*=>"),
    _p("import", r"^\s*import\s+(?:[^\n]+?\s+from\s+)?[\"']([^\"']+)[\"']"),
    _p("export", r"^\s*export\s+\{\s*([^}\n]+)\s*\}"),
]

_GO_PATTERNS = [
    _p("function", r"^\s*func\s+([A-Za-z_]\w*)\s*\("),
    _p("method", r"^\s*func\s*\([^)]*\)\s*([A-Za-z_]\w*)\s*\("),
    _p("type", r"^\s*type\s+([A-Za-z_]\w*)\s+(?:struct|interface)\b"),
    _p("import", r"^\s*import\s+[\"']([^\"']+)[\"']"),
]

_RUST_PATTERNS = [
    _p("function", r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)"),
    _p("struct", r"^\s*(?:pub\s+)?struct\s+([A-Za-z_]\w*)"),
    _p("enum", r"^\s*(?:pub\s+)?enum\s+([A-Za-z_]\w*)"),
    _p("trait", r"^\s*(?:pub\s+)?trait\s+([A-Za-z_]\w*)"),
    _p("type", r"^\s*(?:pub\s+)?type\s+([A-Za-z_]\w*)"),
    _p("import", r"^\s*use\s+([^;]+);"),
]

_JVM_PATTERNS = [
    _p("class", r"^\s*(?:public\s+|private\s+|protected\s+|abstract\s+|final\s+)*class\s+([A-Za-z_]\w*)"),
    _p("interface", r"^\s*(?:public\s+)?interface\s+([A-Za-z_]\w*)"),
    _p("enum", r"^\s*(?:public\s+)?enum\s+([A-Za-z_]\w*)"),
    _p("import", r"^\s*import\s+([A-Za-z_][\w.*]+)\s*;"),
    _p("method", r"^\s*(?:public|private|protected|static|final|async|virtual|override|synchronized|native|abstract|\s)+\s+[\w<>,.?\[\]]+\s+([A-Za-z_]\w*)\s*\("),
]

_C_PATTERNS = [
    _p("type", r"^\s*(?:typedef\s+)?(?:struct|enum|union)\s+([A-Za-z_]\w*)"),
    _p("class", r"^\s*class\s+([A-Za-z_]\w*)"),
    _p("function", r"^\s*[A-Za-z_][\w\s:*&<>]*\s+([A-Za-z_]\w*)\s*\([^;\n]*\)\s*\{"),
    _p("import", r"^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]"),
]

_PHP_PATTERNS = [
    _p("class", r"^\s*(?:final\s+|abstract\s+)?class\s+([A-Za-z_]\w*)"),
    _p("interface", r"^\s*interface\s+([A-Za-z_]\w*)"),
    _p("trait", r"^\s*trait\s+([A-Za-z_]\w*)"),
    _p("function", r"^\s*(?:public\s+|private\s+|protected\s+|static\s+)*function\s+([A-Za-z_]\w*)"),
    _p("import", r"^\s*use\s+([^;]+);"),
]

_RUBY_PATTERNS = [
    _p("class", r"^\s*class\s+([A-Z]\w*(?:::\w+)*)"),
    _p("module", r"^\s*module\s+([A-Z]\w*(?:::\w+)*)"),
    _p("method", r"^\s*def\s+(?:self\.)?([A-Za-z_]\w*[!?=]?)"),
    _p("import", r"^\s*require(?:_relative)?\s+[\"']([^\"']+)[\"']"),
]


class SymbolProviderRegistry:
    def __init__(self) -> None:
        providers: list[SymbolProvider] = [
            PythonProvider(),
            RegexProvider("javascript", (".js", ".jsx", ".mjs", ".cjs"), _JS_PATTERNS),
            RegexProvider("typescript", (".ts", ".tsx", ".mts", ".cts"), _JS_PATTERNS),
            RegexProvider("go", (".go",), _GO_PATTERNS),
            RegexProvider("rust", (".rs",), _RUST_PATTERNS),
            RegexProvider("java", (".java",), _JVM_PATTERNS),
            RegexProvider("csharp", (".cs",), _JVM_PATTERNS),
            RegexProvider("c_cpp", (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp"), _C_PATTERNS),
            RegexProvider("php", (".php",), _PHP_PATTERNS),
            RegexProvider("ruby", (".rb",), _RUBY_PATTERNS),
        ]
        self._by_suffix = {
            suffix: provider
            for provider in providers
            for suffix in provider.suffixes
        }

    @property
    def suffixes(self) -> frozenset[str]:
        return frozenset(self._by_suffix)

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self._by_suffix

    def extract(self, path: Path, source: str) -> list[SymbolRecord]:
        provider = self._by_suffix.get(path.suffix.lower())
        if provider is None:
            return []
        return provider.extract(path, source)
