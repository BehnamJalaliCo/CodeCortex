"""Build a local knowledge graph from repository structure and Python syntax."""

from __future__ import annotations

import ast
from pathlib import Path

from codecortex.indexing.graph import GraphEdge, GraphNode, ProjectGraph

_EXCLUDED = {
    ".git",
    ".codecortex",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
}


class ProjectIndexer:
    def __init__(self, root: Path, max_files: int = 5_000) -> None:
        self.root = root.resolve()
        self.max_files = max_files

    def _files(self) -> list[Path]:
        files: list[Path] = []
        for path in self.root.rglob("*"):
            if len(files) >= self.max_files:
                break
            if not path.is_file():
                continue
            relative = path.relative_to(self.root)
            if any(part in _EXCLUDED for part in relative.parts):
                continue
            files.append(path)
        return files

    @staticmethod
    def _module_name(relative: Path) -> str | None:
        if relative.suffix != ".py":
            return None
        parts = list(relative.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts) if parts else None

    def build(self) -> ProjectGraph:
        files = self._files()
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        node_ids: set[str] = set()

        module_targets: dict[str, str] = {}
        for path in files:
            relative = path.relative_to(self.root)
            file_id = f"file:{relative.as_posix()}"
            nodes.append(
                GraphNode(
                    id=file_id,
                    kind="file",
                    name=relative.name,
                    path=relative.as_posix(),
                    metadata={"extension": relative.suffix.lower()},
                )
            )
            node_ids.add(file_id)
            module_name = self._module_name(relative)
            if module_name:
                module_targets[module_name] = file_id

        for path in files:
            relative = path.relative_to(self.root)
            if relative.suffix != ".py":
                continue
            file_id = f"file:{relative.as_posix()}"
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(path))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue

            for item in ast.walk(tree):
                if isinstance(item, ast.ClassDef):
                    self._add_symbol(nodes, edges, node_ids, file_id, relative, item.name, "class", item.lineno)
                elif isinstance(item, ast.AsyncFunctionDef):
                    self._add_symbol(
                        nodes,
                        edges,
                        node_ids,
                        file_id,
                        relative,
                        item.name,
                        "async_function",
                        item.lineno,
                    )
                elif isinstance(item, ast.FunctionDef):
                    self._add_symbol(
                        nodes,
                        edges,
                        node_ids,
                        file_id,
                        relative,
                        item.name,
                        "function",
                        item.lineno,
                    )
                elif isinstance(item, ast.Import):
                    for alias in item.names:
                        self._add_import(nodes, edges, node_ids, module_targets, file_id, alias.name)
                elif isinstance(item, ast.ImportFrom) and item.module:
                    self._add_import(nodes, edges, node_ids, module_targets, file_id, item.module)

        return ProjectGraph(nodes=nodes, edges=edges)

    @staticmethod
    def _add_symbol(
        nodes: list[GraphNode],
        edges: list[GraphEdge],
        node_ids: set[str],
        file_id: str,
        relative: Path,
        name: str,
        kind: str,
        line: int,
    ) -> None:
        symbol_id = f"symbol:{relative.as_posix()}:{line}:{name}"
        if symbol_id in node_ids:
            return
        node_ids.add(symbol_id)
        nodes.append(
            GraphNode(
                id=symbol_id,
                kind=kind,
                name=name,
                path=relative.as_posix(),
                line=line,
            )
        )
        edges.append(GraphEdge(source=file_id, target=symbol_id, kind="defines"))

    @staticmethod
    def _add_import(
        nodes: list[GraphNode],
        edges: list[GraphEdge],
        node_ids: set[str],
        module_targets: dict[str, str],
        file_id: str,
        module: str,
    ) -> None:
        target = module_targets.get(module)
        if target is None:
            target = f"module:{module}"
            if target not in node_ids:
                node_ids.add(target)
                nodes.append(GraphNode(id=target, kind="module", name=module))
        edges.append(GraphEdge(source=file_id, target=target, kind="imports"))
