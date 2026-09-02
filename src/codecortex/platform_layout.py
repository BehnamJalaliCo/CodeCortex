"""Repository layout contract for the Platform architecture."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LayoutReport:
    valid: bool
    missing: tuple[str, ...]


def validate_layout(root: Path, manifest_path: Path | None = None) -> LayoutReport:
    manifest = manifest_path or root / "platform" / "layout.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("version") != 1:
        raise ValueError("unsupported platform layout version")
    paths = [str(item) for item in payload.get("required_paths", [])]
    paths.extend(str(item) for item in payload.get("logical_components", {}).values())
    missing = tuple(path for path in paths if not (root / path).exists())
    return LayoutReport(not missing, missing)
