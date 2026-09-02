"""Approval-gated semantic editing workflow for the web control plane."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from codecortex.editing import EditService
from codecortex.indexing.impact import ImpactAnalyzer
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.runtime import CortexRuntime

EditOperation = Literal["rename", "replace", "insert_before", "insert_after"]


@dataclass(slots=True)
class SafeEditService:
    runtime: CortexRuntime

    def _file(self, path: str) -> Path:
        candidate = (self.runtime.config.project_root / path).resolve()
        try:
            candidate.relative_to(self.runtime.config.project_root)
        except ValueError as exc:
            raise ValueError("edit path escapes project root") from exc
        if not candidate.is_file():
            raise ValueError("edit target is not a file")
        return candidate

    @staticmethod
    def _hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def preview(self, operation: EditOperation, path: str, name_path: str, *, new_name: str = "", body: str = "") -> dict[str, Any]:
        target = self._file(path)
        backend = EditService(self.runtime).backend()
        preflight = backend.preflight_symbol(name_path, path)
        graph, _ = IncrementalGraphIndex(self.runtime.config.project_root).refresh()
        try:
            impact = ImpactAnalyzer(graph).analyze(name_path.split("/")[-1].split(".")[-1])
            impact_payload = {
                "risk_score": impact.risk_score,
                "direct": len(impact.direct),
                "indirect": len(impact.indirect),
                "affected_tests": [item.node.path or item.node.name for item in impact.affected_tests],
            }
        except ValueError:
            impact_payload = {"risk_score": 0.0, "direct": 0, "indirect": 0, "affected_tests": []}
        return {
            "operation": operation,
            "path": path,
            "name_path": name_path,
            "new_name": new_name if operation == "rename" else None,
            "body_preview": body[:4000] if operation != "rename" else None,
            "file_sha256": self._hash(target),
            "preflight": preflight,
            "impact": impact_payload,
            "requires_approval": True,
        }

    def apply(self, operation: EditOperation, path: str, name_path: str, *, expected_file_sha256: str, approved: bool, new_name: str = "", body: str = "") -> dict[str, Any]:
        if not approved:
            raise PermissionError("explicit approval is required")
        target = self._file(path)
        if self._hash(target) != expected_file_sha256:
            raise RuntimeError("file changed after preview; generate a new preview")
        editor = EditService(self.runtime)
        if operation == "rename":
            result = editor.rename(path, name_path, new_name)
        elif operation == "replace":
            result = editor.replace(path, name_path, body)
        elif operation == "insert_before":
            result = editor.insert_before(path, name_path, body)
        elif operation == "insert_after":
            result = editor.insert_after(path, name_path, body)
        else:
            raise ValueError(f"unknown edit operation: {operation}")
        return {"operation": operation, "path": path, "name_path": name_path, "result": result, "file_sha256": self._hash(target)}
