"""Language-aware parsing, type discovery, and structural extraction."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from codecortex.languages.native import TreeSitterParserProvider


@dataclass(frozen=True, slots=True)
class ParsedUnit:
    name: str
    kind: str
    line: int
    end_line: int | None = None
    signature: str | None = None
    return_type: str | None = None
    type_parameters: tuple[str, ...] = ()
    bases: tuple[str, ...] = ()
    modifiers: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    annotations: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LanguageSpec:
    name: str
    suffixes: tuple[str, ...]
    parser: str


class LanguageRegistry:
    """Use precise Python AST, optional Tree-sitter grammars, then conservative fallback."""

    _SPECS = (
        LanguageSpec("python", (".py",), "python_ast"),
        LanguageSpec("typescript", (".ts", ".tsx"), "native"),
        LanguageSpec("javascript", (".js", ".jsx", ".mjs", ".cjs"), "native"),
        LanguageSpec("go", (".go",), "native"),
        LanguageSpec("rust", (".rs",), "native"),
        LanguageSpec("java", (".java",), "native"),
        LanguageSpec("c", (".c", ".h"), "native"),
        LanguageSpec("cpp", (".cc", ".cpp", ".cxx", ".hpp", ".hh"), "native"),
        LanguageSpec("csharp", (".cs",), "native"),
        LanguageSpec("php", (".php",), "native"),
        LanguageSpec("ruby", (".rb",), "native"),
    )

    def __init__(self, *, native: bool = True) -> None:
        self.native = (
            TreeSitterParserProvider()
            if native and TreeSitterParserProvider.available()
            else None
        )

    def language_for(self, path: Path) -> LanguageSpec | None:
        suffix = path.suffix.lower()
        return next((spec for spec in self._SPECS if suffix in spec.suffixes), None)

    def parse(self, path: Path, source: str) -> list[ParsedUnit]:
        spec = self.language_for(path)
        if spec is None:
            return []
        if spec.parser == "python_ast":
            return self._parse_python(source)
        if self.native is not None:
            try:
                units = self.native.parse(spec.name, source)
            except Exception:
                units = []
            if units:
                return [
                    ParsedUnit(
                        name=item.name,
                        kind=item.kind,
                        line=item.line,
                        end_line=item.end_line,
                        signature=item.signature,
                        return_type=item.return_type,
                        bases=item.bases,
                        references=item.references,
                    )
                    for item in units
                ]
        return self._parse_structural(spec.name, source)

    def _parse_python(self, source: str) -> list[ParsedUnit]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        units: list[ParsedUnit] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                units.append(
                    ParsedUnit(
                        name=node.name,
                        kind="class",
                        line=node.lineno,
                        end_line=getattr(node, "end_lineno", None),
                        bases=tuple(ast.unparse(base) for base in node.bases),
                        type_parameters=tuple(
                            getattr(item, "name", ast.unparse(item))
                            for item in getattr(node, "type_params", [])
                        ),
                    )
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [arg.arg for arg in node.args.posonlyargs + node.args.args]
                args.extend(f"*{arg.arg}" for arg in node.args.kwonlyargs)
                if node.args.vararg:
                    args.append(f"*{node.args.vararg.arg}")
                if node.args.kwarg:
                    args.append(f"**{node.args.kwarg.arg}")
                refs = tuple(
                    child.id
                    for child in ast.walk(node)
                    if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
                )
                units.append(
                    ParsedUnit(
                        name=node.name,
                        kind=(
                            "async_function"
                            if isinstance(node, ast.AsyncFunctionDef)
                            else "function"
                        ),
                        line=node.lineno,
                        end_line=getattr(node, "end_lineno", None),
                        signature=f"({', '.join(args)})",
                        return_type=ast.unparse(node.returns) if node.returns else None,
                        references=refs,
                        annotations={
                            arg.arg: ast.unparse(arg.annotation)
                            for arg in node.args.posonlyargs + node.args.args
                            if arg.annotation is not None
                        },
                    )
                )
        return units

    def _parse_structural(self, language: str, source: str) -> list[ParsedUnit]:
        units: list[ParsedUnit] = []
        patterns = self._patterns(language)
        for line_no, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            for kind, pattern in patterns:
                match = pattern.search(stripped)
                if not match:
                    continue
                name = match.group("name")
                bases = tuple(
                    item.strip()
                    for item in (match.groupdict().get("bases") or "").split(",")
                    if item.strip()
                )
                units.append(
                    ParsedUnit(
                        name=name,
                        kind=kind,
                        line=line_no,
                        signature=match.groupdict().get("signature"),
                        return_type=match.groupdict().get("return"),
                        bases=bases,
                        modifiers=tuple(
                            item
                            for item in (match.groupdict().get("mods") or "").split()
                            if item
                        ),
                    )
                )
                break
        return units

    @staticmethod
    def _patterns(language: str) -> tuple[tuple[str, re.Pattern[str]], ...]:
        common_class = re.compile(
            r"(?P<mods>(?:(?:export|public|private|protected|abstract|final|sealed|static)\s+)*)"
            r"(?:class|interface|trait|struct|enum)\s+(?P<name>[A-Za-z_][\w$]*)"
            r"(?:\s+(?:extends|implements|:)\s+(?P<bases>[^\{]+))?"
        )
        c_like_function = re.compile(
            r"(?P<mods>(?:(?:export|public|private|protected|static|async|virtual|override|final|unsafe)\s+)*)"
            r"(?:(?P<return>[A-Za-z_][\w:<>,\[\]?*& ]*)\s+)?"
            r"(?P<name>[A-Za-z_][\w$]*)\s*(?P<signature>\([^;{}]*\))\s*(?:\{|=>)"
        )
        function_keyword = re.compile(
            r"(?P<mods>(?:(?:export|async|pub|unsafe)\s+)*)"
            r"(?:function|fn|func|def)\s+(?P<name>[A-Za-z_][\w$!?]*)\s*(?P<signature>\([^)]*\))"
            r"(?:\s*(?:->|:)\s*(?P<return>[^\{=]+))?"
        )
        arrow = re.compile(
            r"(?:(?:export|const|let|var)\s+)+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*"
            r"(?:async\s+)?(?P<signature>\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
        )
        ruby_class = re.compile(r"(?:class|module)\s+(?P<name>[A-Za-z_][\w:]*)")
        if language == "ruby":
            return (("class", ruby_class), ("function", function_keyword))
        if language in {"typescript", "javascript"}:
            return (
                ("class", common_class),
                ("function", function_keyword),
                ("function", arrow),
                ("function", c_like_function),
            )
        return (
            ("class", common_class),
            ("function", function_keyword),
            ("function", c_like_function),
        )

    def resolve_types(self, units: list[ParsedUnit]) -> dict[str, set[str]]:
        names = {unit.name for unit in units}
        resolved: dict[str, set[str]] = {}
        for unit in units:
            candidates = set(unit.bases)
            candidates.update(unit.annotations.values())
            if unit.return_type:
                candidates.add(unit.return_type)
            matches = {
                name
                for name in names
                if any(
                    re.search(rf"\b{re.escape(name)}\b", candidate)
                    for candidate in candidates
                )
            }
            resolved[unit.name] = matches
        return resolved
