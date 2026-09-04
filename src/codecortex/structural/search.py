"""Structural search: syntax-aware matching bounded to the project root."""

from __future__ import annotations

from pathlib import Path

from codecortex.config import CortexConfig, StructuralConfig
from codecortex.structural.engine import EngineStatus, StructuralEngine
from codecortex.structural.models import StructuralError, StructuralMatch


def contain_path(root: Path, value: str) -> Path:
    """Resolve ``value`` under ``root``, rejecting traversal and symlink escapes.

    Raises:
        StructuralError: when the path would leave the project root.
    """
    candidate = Path(value)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise StructuralError(f"path escapes the project root: {value}")
    return resolved


class StructuralSearch:
    """Run structural queries and normalize engine output into typed matches."""

    def __init__(
        self,
        root: Path,
        config: CortexConfig | None = None,
        engine: StructuralEngine | None = None,
    ) -> None:
        self.root = root.resolve()
        self.config = config or CortexConfig.load(self.root)
        self.settings: StructuralConfig = self.config.structural
        self.engine = engine or StructuralEngine(self.root, self.settings)

    def status(self) -> EngineStatus:
        return self.engine.status()

    def _scope(self, paths: tuple[str, ...]) -> tuple[str, ...]:
        """Validate the requested search scope, keeping it inside the project."""
        if not paths:
            return ()
        scope: list[str] = []
        for value in paths:
            resolved = contain_path(self.root, value)
            if not resolved.exists():
                raise StructuralError(f"search path does not exist: {value}")
            scope.append(
                "." if resolved == self.root else resolved.relative_to(self.root).as_posix()
            )
        return tuple(scope)

    def _match(self, record: dict[str, object], rule_id: str | None) -> StructuralMatch | None:
        raw_file = record.get("file")
        raw_range = record.get("range")
        if not isinstance(raw_file, str) or not isinstance(raw_range, dict):
            return None
        try:
            resolved = contain_path(self.root, raw_file)
        except StructuralError:
            # A match outside the project root is dropped rather than reported.
            return None
        start = raw_range.get("start")
        end = raw_range.get("end")
        offsets = raw_range.get("byteOffset")
        if not isinstance(start, dict) or not isinstance(end, dict):
            return None
        captures: dict[str, str] = {}
        meta = record.get("metaVariables")
        if isinstance(meta, dict):
            single = meta.get("single")
            if isinstance(single, dict):
                for name, node in single.items():
                    if isinstance(node, dict) and isinstance(node.get("text"), str):
                        captures[str(name)] = str(node["text"])
            transformed = meta.get("transformed")
            if isinstance(transformed, dict):
                for name, value in transformed.items():
                    if isinstance(value, str):
                        captures.setdefault(str(name), value)
        replacement = record.get("replacement")
        return StructuralMatch(
            path=resolved.relative_to(self.root).as_posix(),
            start_line=int(start.get("line", 0)) + 1,
            start_column=int(start.get("column", 0)) + 1,
            end_line=int(end.get("line", 0)) + 1,
            end_column=int(end.get("column", 0)) + 1,
            matched_text=str(record.get("text", "")),
            captures=captures,
            rule_id=rule_id,
            language=str(record.get("language", "")),
            replacement=replacement if isinstance(replacement, str) else None,
            byte_start=int(offsets.get("start", 0)) if isinstance(offsets, dict) else 0,
            byte_end=int(offsets.get("end", 0)) if isinstance(offsets, dict) else 0,
        )

    def search(
        self,
        pattern: str,
        language: str,
        *,
        rewrite: str | None = None,
        include: tuple[str, ...] = (),
        exclude: tuple[str, ...] = (),
        paths: tuple[str, ...] = (),
        limit: int | None = None,
        rule_id: str | None = None,
    ) -> list[StructuralMatch]:
        """Return typed matches for a structural pattern."""
        maximum = min(limit or self.settings.max_results, self.settings.max_results)
        matches: list[StructuralMatch] = []
        for record in self.engine.search(
            pattern=pattern,
            language=language,
            rewrite=rewrite,
            include=include,
            exclude=exclude,
            paths=self._scope(paths),
        ):
            match = self._match(record, rule_id)
            if match is not None:
                matches.append(match)
                if len(matches) >= maximum:
                    break
        matches.sort(key=lambda item: (item.path, item.start_line, item.start_column))
        return matches
