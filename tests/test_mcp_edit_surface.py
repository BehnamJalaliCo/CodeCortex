import pytest

from codecortex.mcp.extended import ExtendedMCPApplication
from codecortex.runtime import build_runtime


def test_extended_mcp_lists_guarded_edit_tools(tmp_path):
    names = {tool["name"] for tool in ExtendedMCPApplication(build_runtime(tmp_path)).tools()}
    assert {
        "cortex_rename_symbol",
        "cortex_replace_symbol_body",
        "cortex_insert_before_symbol",
        "cortex_insert_after_symbol",
    } <= names


@pytest.mark.asyncio
async def test_edit_requires_mature_symbol_backend(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("class Example:\n    pass\n", encoding="utf-8")
    app = ExtendedMCPApplication(build_runtime(tmp_path))
    with pytest.raises(RuntimeError, match="mature symbol backend"):
        await app.call(
            "cortex_rename_symbol",
            {"path": "app.py", "name_path": "Example", "new_name": "Renamed"},
        )
