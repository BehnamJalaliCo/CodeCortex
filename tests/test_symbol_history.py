import subprocess

from codecortex.git_intelligence import GitIntelligence


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_symbol_history_returns_commits_and_blame(tmp_path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "Test User")
    _git(tmp_path, "config", "user.email", "test@example.com")
    source = tmp_path / "service.py"
    source.write_text("def run():\n    return 1\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "add run")
    source.write_text("def run():\n    return 2\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "change run")

    history = GitIntelligence(tmp_path).symbol_history("service.py", 1, 2)
    assert history.commits
    assert history.blame
    assert history.owners[0].name == "Test User"
