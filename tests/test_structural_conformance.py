"""Conformance tests against the real structural engine binary.

The rest of the structural suite runs against an in-repository stub, which
keeps normal CI free of an optional extra. These tests run only when the real
engine is installed, and they exist because a stub can only reproduce the
record shape its author believed in. Everything asserted here was observed from
the pinned release's actual output.

They are skipped, not failed, when the engine is absent — and a skip means the
real binary was not exercised.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from codecortex.config import CortexConfig, StructuralConfig
from codecortex.structural.engine import (
    SUCCESS_EXIT_CODES,
    TESTED_ENGINE_VERSION,
    StructuralEngine,
    parse_engine_version,
)
from codecortex.structural.models import StructuralError
from codecortex.structural.search import StructuralSearch

ENGINE = shutil.which("ast-grep")

pytestmark = pytest.mark.skipif(
    ENGINE is None,
    reason="SKIPPED - the optional structural engine is not installed",
)

PATTERN = "old_api($X)"

SOURCE = '''\
def handler():
    old_api(1)
    other(2)
    old_api("🚀 emoji argument")
    old_api(سلام)


# old_api(3) appears here only in prose, and must not match.
TEXT = "call old_api(4) to migrate"
'''


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "module.py").write_text(SOURCE, encoding="utf-8")
    (root / "pkg" / "other.py").write_text("def f():\n    old_api(9)\n", encoding="utf-8")
    (root / "vendor").mkdir()
    (root / "vendor" / "ignored.py").write_text("old_api(0)\n", encoding="utf-8")
    return root


def _search(root: Path, **overrides: object) -> StructuralSearch:
    config = CortexConfig(project_root=root, structural=StructuralConfig(**overrides))  # type: ignore[arg-type]
    return StructuralSearch(root, config)


# -- engine identity --------------------------------------------------------


def test_the_installed_engine_is_the_tested_release(tmp_path: Path) -> None:
    status = StructuralEngine(tmp_path).status()
    assert status.available
    assert status.engine_version, status.version
    if not status.verified_version:
        pytest.skip(
            f"SKIPPED - installed engine {status.engine_version} is not the "
            f"tested release {TESTED_ENGINE_VERSION}"
        )
    assert status.verified_version
    assert status.version_warning == ""


@pytest.mark.parametrize(
    ("banner", "expected"),
    [
        ("ast-grep 0.45.3", "0.45.3"),
        ("ast-grep 1.0.0-beta.2", "1.0.0-beta.2"),
        ("no version here", ""),
    ],
)
def test_version_parsing_reads_the_engine_banner(banner: str, expected: str) -> None:
    assert parse_engine_version(banner) == expected


def test_an_untested_engine_version_is_reported_not_hidden(tmp_path: Path) -> None:
    """An unverified combination must not be presented as a verified one."""
    from codecortex.structural.engine import EngineStatus

    unverified = EngineStatus(available=True, executable="x", version="ast-grep 9.9.9")
    assert not unverified.verified_version
    assert "9.9.9" in unverified.version_warning
    assert TESTED_ENGINE_VERSION in unverified.version_warning
    assert unverified.to_dict()["verified_version"] is False


# -- JSON stream records ----------------------------------------------------


def test_one_match_is_parsed_from_the_real_stream(project: Path) -> None:
    matches = _search(project).search(PATTERN, "python", paths=("pkg/other.py",))
    assert len(matches) == 1
    match = matches[0]
    assert match.path == "pkg/other.py"
    assert match.matched_text == "old_api(9)"
    assert match.captures == {"X": "9"}
    assert match.language.lower() == "python"
    # Public coordinates are one-based; the engine emits zero-based.
    assert (match.start_line, match.start_column) == (2, 5)
    assert match.byte_end > match.byte_start


def test_many_matches_are_parsed_and_ordered(project: Path) -> None:
    matches = _search(project).search(PATTERN, "python")
    assert len(matches) >= 4
    assert matches == sorted(
        matches, key=lambda item: (item.path, item.start_line, item.start_column)
    )
    assert {item.path for item in matches} == {
        "pkg/module.py",
        "pkg/other.py",
        "vendor/ignored.py",
    }


def test_no_match_is_an_empty_result_not_an_error(project: Path) -> None:
    """The engine exits non-zero when nothing matched; that is not a failure."""
    assert 1 in SUCCESS_EXIT_CODES
    assert _search(project).search("never_called($X)", "python") == []


def test_structural_matching_ignores_prose_that_merely_mentions_the_call(
    project: Path,
) -> None:
    """This is the whole reason for using an AST engine over a text scan."""
    matches = _search(project).search(PATTERN, "python", paths=("pkg/module.py",))
    lines = {item.start_line for item in matches}
    source = SOURCE.splitlines()
    assert all("only in prose" not in source[line - 1] for line in lines)
    assert not any(item.matched_text == "old_api(3)" for item in matches)
    # The string literal on the TEXT line is not code, so it does not match.
    assert not any("to migrate" in item.matched_text for item in matches)


def test_unicode_arguments_survive_the_round_trip(project: Path) -> None:
    matches = _search(project).search(PATTERN, "python", paths=("pkg/module.py",))
    captures = {item.captures.get("X", "") for item in matches}
    assert '"🚀 emoji argument"' in captures
    assert "سلام" in captures


def test_engine_columns_are_character_columns(project: Path) -> None:
    """Verified against the real binary: a column counts characters, not bytes.

    The emoji line is where a byte-based column would diverge, and the engine
    reports byteOffset separately for exactly that reason.
    """
    matches = _search(project).search(PATTERN, "python", paths=("pkg/module.py",))
    emoji = next(item for item in matches if "🚀" in item.matched_text)
    line = SOURCE.splitlines()[emoji.start_line - 1]
    assert line[emoji.start_column - 1 :].startswith("old_api(")
    assert emoji.end_column - emoji.start_column == len(emoji.matched_text)
    # A byte offset would be larger, because the emoji is four bytes.
    assert emoji.byte_end - emoji.byte_start > len(emoji.matched_text)


def test_rewrite_preview_records_carry_a_replacement(project: Path) -> None:
    matches = _search(project).search(
        PATTERN, "python", rewrite="new_api($X)", paths=("pkg/other.py",)
    )
    assert [item.replacement for item in matches] == ["new_api(9)"]
    # A preview must not touch the file.
    assert "old_api(9)" in (project / "pkg" / "other.py").read_text(encoding="utf-8")


def test_globs_exclude_paths_from_the_real_search(project: Path) -> None:
    matches = _search(project).search(PATTERN, "python", exclude=("vendor/**",))
    assert {item.path for item in matches} == {"pkg/module.py", "pkg/other.py"}


def test_the_result_limit_is_enforced(project: Path) -> None:
    assert len(_search(project, max_results=2).search(PATTERN, "python")) == 2


# -- failure modes ----------------------------------------------------------


def test_a_malformed_pattern_is_reported_rather_than_returning_nothing(
    project: Path,
) -> None:
    """The engine exits 0 with a warning and no matches for a broken pattern.

    Measured against the real binary: an unbalanced pattern is not an error
    exit. Without surfacing the warning, "your pattern is invalid" and "nothing
    in this repository matches" are the same empty list.
    """
    with pytest.raises(StructuralError, match="not valid for this language"):
        _search(project).search("old_api($X", "python")


def test_a_valid_pattern_with_no_matches_is_not_an_error(project: Path) -> None:
    """The contrast case: exit 1, no warning, and an honest empty result."""
    assert _search(project).search("definitely_absent($X)", "python") == []


def test_an_unknown_language_is_reported_as_an_error(project: Path) -> None:
    with pytest.raises(StructuralError, match="not supported"):
        _search(project).search(PATTERN, "not-a-real-language")


def test_truncated_engine_output_stops_cleanly(project: Path) -> None:
    """A response cut off by the output cap must not raise a parse error."""
    engine = StructuralEngine(project, StructuralConfig(max_output_bytes=120))
    records = list(engine.search(pattern=PATTERN, language="python"))
    # Whatever survived the cap must be well-formed records, not fragments.
    assert all(isinstance(item, dict) for item in records)
    assert all("range" in item for item in records)


def test_the_engine_never_reaches_a_shell(project: Path) -> None:
    """A pattern containing shell metacharacters is an argument, not a command."""
    marker = project / "pwned.txt"
    search = _search(project)
    for hostile in (f"old_api($X); touch {marker}", f"$(touch {marker})", "`id`"):
        try:
            search.search(hostile, "python")
        except StructuralError:
            pass
        assert not marker.exists(), hostile


def test_matches_outside_the_project_root_are_dropped(project: Path, tmp_path: Path) -> None:
    """A record naming a path outside the root is discarded, not resolved."""
    outside = tmp_path / "outside.py"
    outside.write_text("old_api(1)\n", encoding="utf-8")
    search = _search(project)
    record = json.loads(
        json.dumps(
            {
                "file": str(outside),
                "text": "old_api(1)",
                "language": "Python",
                "range": {
                    "start": {"line": 0, "column": 0},
                    "end": {"line": 0, "column": 10},
                    "byteOffset": {"start": 0, "end": 10},
                },
            }
        )
    )
    assert search._match(record, None) is None


def test_a_search_path_outside_the_root_is_refused(project: Path) -> None:
    with pytest.raises(StructuralError, match="escapes the project root"):
        _search(project).search(PATTERN, "python", paths=("../",))
