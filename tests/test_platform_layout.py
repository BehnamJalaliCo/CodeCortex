from pathlib import Path

from codecortex.platform_layout import validate_layout


def test_platform_repository_layout_is_complete() -> None:
    report = validate_layout(Path.cwd())
    assert report.valid, f"missing platform paths: {report.missing}"
