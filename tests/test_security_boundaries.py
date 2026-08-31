import pytest

from codecortex.backends.symbols import SymbolBackendAdapter


def test_symbol_edit_rejects_parent_escape(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    adapter = SymbolBackendAdapter(project)
    with pytest.raises(ValueError, match="inside the project root"):
        adapter._relative_path("../outside.py")


def test_symbol_edit_rejects_absolute_escape(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    adapter = SymbolBackendAdapter(project)
    with pytest.raises(ValueError, match="inside the project root"):
        adapter._relative_path(str(outside))


def test_symbol_edit_rejects_symlink_escape(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    link = project / "link.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")
    adapter = SymbolBackendAdapter(project)
    with pytest.raises(ValueError, match="inside the project root"):
        adapter._relative_path("link.py")
