from codecortex.indexing.incremental import IncrementalIndex


def test_incremental_index_detects_changes(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    index = IncrementalIndex(tmp_path)

    first = index.refresh()
    assert first.added == ("app.py",)
    assert first.changed == ()

    second = index.refresh()
    assert second.added == ()
    assert second.changed == ()
    assert second.unchanged == 1

    source.write_text("value = 2\n", encoding="utf-8")
    third = index.refresh()
    assert third.changed == ("app.py",)

    source.unlink()
    fourth = index.refresh()
    assert fourth.removed == ("app.py",)
