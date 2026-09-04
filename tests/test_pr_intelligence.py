import subprocess

from codecortex.indexing.indexer import ProjectIndexer
from codecortex.pr_intelligence import PRIntelligence


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_pr_intelligence_maps_diff_to_symbols(tmp_path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "Test User")
    _git(tmp_path, "config", "user.email", "test@example.com")
    source = tmp_path / "auth.py"
    source.write_text("def refresh_token():\n    return 1\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    source.write_text("def refresh_token():\n    return 2\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "change")

    graph = ProjectIndexer(tmp_path).build()
    report = PRIntelligence(tmp_path, graph).analyze(base)
    assert report.files[0].path == "auth.py"
    assert report.files[0].additions == 1
    assert any(item.node.name == "refresh_token" for item in report.symbols)
    assert report.risk_level in {"low", "medium", "high"}
