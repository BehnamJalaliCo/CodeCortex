import subprocess

from codecortex.git_intelligence import GitIntelligence


def _run(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_git_intelligence_tracks_churn_and_cochange(tmp_path):
    _run(tmp_path, "init")
    _run(tmp_path, "config", "user.name", "Test User")
    _run(tmp_path, "config", "user.email", "test@example.com")
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 1\n", encoding="utf-8")
    _run(tmp_path, "add", ".")
    _run(tmp_path, "commit", "-m", "first")
    (tmp_path / "a.py").write_text("a = 2\n", encoding="utf-8")
    _run(tmp_path, "add", ".")
    _run(tmp_path, "commit", "-m", "second")

    report = GitIntelligence(tmp_path).analyze()
    assert report.commits == 2
    assert report.hot_files[0].path == "a.py"
    assert report.hot_files[0].changes == 2
    assert report.authors[0].commits == 2
    assert any(item.left == "a.py" and item.right == "b.py" for item in report.co_changes)
