import json
from pathlib import Path


def test_architecture_rules_cover_web_legacy_dashboard_and_engines() -> None:
    payload = json.loads(Path("platform/architecture_rules.json").read_text(encoding="utf-8"))
    ids = {rule["id"] for rule in payload["rules"]}
    assert "web-no-storage" in ids
    assert "legacy-dashboard-is-not-platform" in ids
    assert "engines-no-full-indexer" in ids


def test_web_does_not_reference_low_level_repository_storage() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in Path("web/src").rglob("*.tsx"))
    assert "sqlite3" not in text
    assert "ProjectIndexer" not in text
    assert ".codecortex/" not in text
