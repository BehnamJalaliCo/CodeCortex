"""Security boundaries for the evidence layers.

Each case is an input CodeCortex does not control: an index file that may be
hostile or corrupt, a documentation response from a remote service, a worktree
that changes underneath a pending rewrite. The requirement throughout is that
CodeCortex fails closed with a typed error rather than producing a plausible
wrong answer or touching something outside the project root.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from codecortex.config import CortexConfig, PrecisionIndexConfig
from codecortex.evidence.models import EvidenceKind
from codecortex.precision.importer import import_index, normalize_index_path
from codecortex.precision.index import PrecisionIndexStore
from codecortex.precision.models import PrecisionIndexError
from codecortex.precision.provider import PrecisionEvidenceProvider
from codecortex.precision.schema import PositionEncoding
from codecortex.precision.wire import (
    encode_bytes_field,
    encode_string_field,
    encode_varint_field,
)
from codecortex.structural.models import StructuralError
from codecortex.structural.search import contain_path
from tests.fixtures.precision_index import (
    DEFINITION,
    Document,
    IndexBuilder,
    Occurrence,
    symbol,
)

TARGET = symbol("app", "mod/`handler`().")


# -- indexed document paths -------------------------------------------------


def test_a_symlinked_document_is_never_followed_out_of_the_project(
    tmp_path: Path,
) -> None:
    """The protocol forbids a symlink document; the root is re-checked anyway.

    A path that is textually valid can still resolve outside the project once
    a symlink is involved, so containment is verified at join time rather than
    inferred from the string having looked acceptable.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.py"
    secret.write_text("SECRET = 'do not read'\n", encoding="utf-8")

    root = tmp_path / "project"
    root.mkdir()
    (root / "mod.py").symlink_to(secret)

    index_path = root / "index.scip"
    index_path.write_bytes(
        IndexBuilder()
        .add(
            Document(
                relative_path="mod.py",
                occurrences=(Occurrence(TARGET, 0, 0, 6, roles=DEFINITION),),
            )
        )
        .encode()
    )
    later = time.time() + 600
    os.utime(index_path, (later, later))

    store = PrecisionIndexStore(root=root)
    document = store.load().document("mod.py")  # type: ignore[union-attr]
    assert document is not None
    # Reading a line for position conversion must refuse the symlink.
    assert store.source_line(document, 0) is None


def test_the_store_refuses_to_map_a_path_outside_the_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    store = PrecisionIndexStore(root=root)
    for hostile in ("/etc/passwd", "../outside.py", str(tmp_path / "elsewhere.py")):
        with pytest.raises(ValueError, match="inside the project root"):
            store.relative_path(hostile)


@pytest.mark.parametrize(
    "hostile",
    [
        "/etc/passwd",
        "../../etc/passwd",
        "a/../../etc/passwd",
        "C:\\Windows\\system32\\config",
        "file:///etc/passwd",
        "a//b.py",
        "./a.py",
        "a/./b.py",
        "\x00",
        "   ",
    ],
)
def test_a_hostile_document_path_fails_the_whole_import(hostile: str) -> None:
    """One bad path rejects the index rather than being quietly dropped.

    A partially imported index would answer some questions correctly and
    others silently wrongly, which is worse than refusing to load it.
    """
    with pytest.raises(PrecisionIndexError):
        normalize_index_path(hostile)

    payload = (
        IndexBuilder()
        .add(
            Document(
                relative_path=hostile,
                occurrences=(Occurrence(TARGET, 0, 0, 6, roles=DEFINITION),),
            )
        )
        .encode()
    )
    with pytest.raises(PrecisionIndexError):
        import_index(payload)


# -- malformed index payloads ----------------------------------------------


def test_invalid_utf8_in_a_text_field_fails_the_import_closed() -> None:
    """Protobuf strings must be UTF-8; a producer may still emit junk.

    The index is refused rather than decoded lossily. A lossy decode would put
    a mangled language or symbol string into the graph, where it would go on
    producing wrong-but-plausible answers.
    """
    document = (
        encode_bytes_field(1, b"mod.py")
        # DocumentField.LANGUAGE carrying an invalid UTF-8 sequence.
        + encode_bytes_field(4, b"\xff\xfe invalid")
        + encode_bytes_field(
            2,
            encode_string_field(2, TARGET)
            + encode_varint_field(3, DEFINITION)
            + encode_bytes_field(
                8, encode_varint_field(1, 0) + encode_varint_field(2, 0) + encode_varint_field(3, 6)
            ),
        )
    )
    payload = encode_bytes_field(1, encode_varint_field(1, 0)) + encode_bytes_field(2, document)
    with pytest.raises(PrecisionIndexError, match="not valid UTF-8"):
        import_index(payload)


def test_an_index_larger_than_the_configured_limit_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    index_path = root / "index.scip"
    index_path.write_bytes(b"\x00" * 4096)
    store = PrecisionIndexStore(root=root, config=PrecisionIndexConfig(max_index_bytes=256))
    status = store.status()
    assert not status.available
    assert "exceeds the configured limit" in status.detail


def test_a_truncated_index_reports_a_typed_error_not_a_partial_result() -> None:
    payload = (
        IndexBuilder()
        .add(
            Document(
                relative_path="mod.py",
                occurrences=(Occurrence(TARGET, 0, 0, 6, roles=DEFINITION),),
            )
        )
        .encode()
    )
    with pytest.raises(PrecisionIndexError, match="malformed"):
        import_index(payload[: len(payload) // 2])


# -- position conversion is not a read primitive ---------------------------


def test_position_conversion_cannot_be_used_to_read_an_arbitrary_file(
    tmp_path: Path,
) -> None:
    """Reading a source line is bounded by the root and by a size limit."""
    root = tmp_path / "project"
    root.mkdir()
    big = root / "mod.py"
    big.write_text("x = 1\n" * 10_000, encoding="utf-8")
    index_path = root / "index.scip"
    index_path.write_bytes(
        IndexBuilder()
        .add(
            Document(
                relative_path="mod.py",
                occurrences=(Occurrence(TARGET, 0, 0, 6, roles=DEFINITION),),
            )
        )
        .encode()
    )
    later = time.time() + 600
    os.utime(index_path, (later, later))

    store = PrecisionIndexStore(root=root, config=PrecisionIndexConfig(max_source_bytes=16))
    document = store.load().document("mod.py")  # type: ignore[union-attr]
    assert document is not None
    assert store.source_line(document, 0) is None


def test_an_unreadable_source_downgrades_rather_than_raising(tmp_path: Path) -> None:
    """A UTF-16 index whose source cannot be read still answers, inexactly.

    The symbol is still right; only the column is uncertain. Dropping the
    evidence would lose a correct answer, and keeping it exact would assert a
    position that was never converted.
    """
    root = tmp_path / "project"
    root.mkdir()
    (root / "mod.py").write_text("def handler(): ...\n", encoding="utf-8")
    index_path = root / "index.scip"
    index_path.write_bytes(
        IndexBuilder()
        .add(
            Document(
                relative_path="mod.py",
                position_encoding=PositionEncoding.UTF16_CODE_UNIT,
                occurrences=(Occurrence(TARGET, 0, 4, 11, roles=DEFINITION),),
            )
        )
        .encode()
    )
    later = time.time() + 600
    os.utime(index_path, (later, later))

    config = CortexConfig(project_root=root)
    config = config.model_copy(
        update={"precision_index": PrecisionIndexConfig(max_source_bytes=1)}
    )
    provider = PrecisionEvidenceProvider(root, config)
    bundle = provider.evidence_for_symbol(TARGET, EvidenceKind.DEFINITION)
    assert bundle.records, "navigation must degrade, not disappear"
    assert not bundle.records[0].exact


# -- structural containment -------------------------------------------------


def test_structural_path_containment_rejects_escapes(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pkg").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "file.py").write_text("x = 1\n", encoding="utf-8")
    (root / "link").symlink_to(outside)

    assert contain_path(root, "pkg") == (root / "pkg").resolve()
    for hostile in ("..", "../outside", str(outside), "link/file.py"):
        with pytest.raises(StructuralError, match="escapes the project root"):
            contain_path(root, hostile)


def test_a_sibling_directory_sharing_a_prefix_is_not_inside_the_root(
    tmp_path: Path,
) -> None:
    """`/a/project-other` must not count as inside `/a/project`."""
    root = tmp_path / "project"
    root.mkdir()
    sibling = tmp_path / "project-other"
    sibling.mkdir()
    (sibling / "file.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(StructuralError, match="escapes the project root"):
        contain_path(root, str(sibling / "file.py"))
