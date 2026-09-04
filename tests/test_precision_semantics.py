"""Protocol-semantics regressions for precision navigation.

Every test here fails against the pre-hardening implementation. They cover the
three ways an index can be read wrongly without raising: a range boundary
treated as inclusive, a column read in the wrong encoding, and a document-local
symbol treated as globally unique.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from codecortex.config import CortexConfig, PrecisionIndexConfig
from codecortex.evidence.models import EvidenceKind, TrustTier
from codecortex.precision.compatibility import EncodingSource, resolve_encoding
from codecortex.precision.importer import decode_project_root, import_index
from codecortex.precision.index import PrecisionIndexStore
from codecortex.precision.models import (
    PrecisionIndex,
    SourceRange,
    is_local_symbol,
    scoped_symbol_key,
)
from codecortex.precision.positions import (
    character_to_protocol,
    encoding_is_undecidable,
    protocol_to_character,
)
from codecortex.precision.provider import PrecisionEvidenceProvider, PrecisionQuery
from codecortex.precision.schema import PositionEncoding
from tests.fixtures.precision_index import (
    DEFINITION,
    Document,
    IndexBuilder,
    Occurrence,
    SymbolInfo,
    column_in,
    symbol,
)

# -- half-open range semantics ---------------------------------------------


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        (5, False),  # before the range
        (6, True),  # at start, inclusive
        (9, True),  # inside
        (12, True),  # end - 1, the last character of the identifier
        (13, False),  # at end, exclusive
        (14, False),  # past the end
    ],
)
def test_single_line_range_is_half_open(column: int, expected: bool) -> None:
    """``start <= caret < end``. A caret at ``end`` belongs to the next token."""
    assert SourceRange(0, 6, 0, 13).contains(0, column) is expected


def test_multi_line_range_start_is_inclusive_and_end_is_exclusive() -> None:
    span = SourceRange(2, 4, 5, 9)
    assert not span.contains(2, 3)
    assert span.contains(2, 4)
    assert span.contains(3, 0)  # an interior line has no column bound
    assert span.contains(3, 9_999)
    assert span.contains(5, 8)
    assert not span.contains(5, 9)
    assert not span.contains(6, 0)


def test_a_zero_width_range_contains_no_position() -> None:
    assert not SourceRange(1, 4, 1, 4).contains(1, 4)


ADJACENT_A = symbol("app", "mod/`a`.")
ADJACENT_B = symbol("app", "mod/`b`.")


def _adjacent_index() -> PrecisionIndex:
    """Two identifiers that touch: ``ab`` where ``a`` is [0,1) and ``b`` is [1,2)."""
    return import_index(
        IndexBuilder()
        .add(
            Document(
                relative_path="m.py",
                occurrences=(
                    Occurrence(ADJACENT_A, 0, 0, 1, roles=DEFINITION),
                    Occurrence(ADJACENT_B, 0, 1, 2, roles=DEFINITION),
                ),
                text="ab\n",
            )
        )
        .encode()
    )


def test_adjacent_occurrences_do_not_overlap() -> None:
    """With an inclusive end, column 1 would match both identifiers.

    The tightest-range tie-break would then resolve the caret to whichever
    symbol sorted first, which is a coin flip rather than a resolution.
    """
    index = _adjacent_index()
    first = index.occurrence_at("m.py", 0, 0)
    second = index.occurrence_at("m.py", 0, 1)
    assert first is not None and first.symbol == ADJACENT_A
    assert second is not None and second.symbol == ADJACENT_B
    assert index.occurrence_at("m.py", 0, 2) is None


# -- position encoding ------------------------------------------------------

# From the schema's own worked example: for "🚀 Woo", 'W' is at byte offset 5,
# UTF-16 offset 3, and code-point offset 2.
ROCKET_LINE = "🚀 Woo"


@pytest.mark.parametrize(
    ("encoding", "protocol_column"),
    [
        (PositionEncoding.UTF8_CODE_UNIT, 5),
        (PositionEncoding.UTF16_CODE_UNIT, 3),
        (PositionEncoding.UTF32_CODE_UNIT, 2),
    ],
)
def test_schema_worked_example_round_trips(
    encoding: PositionEncoding, protocol_column: int
) -> None:
    assert protocol_to_character(ROCKET_LINE, protocol_column, encoding).column == 2
    assert character_to_protocol(ROCKET_LINE, 2, encoding).column == protocol_column


@pytest.mark.parametrize(
    "line_text",
    [
        "value = 1",  # ASCII control case
        "café = 1",  # multi-byte UTF-8, single UTF-16 unit
        "سلام = 1",  # Persian, multi-byte UTF-8
        "🙂🙂 = 1",  # astral plane, surrogate pairs in UTF-16
        "日本語 = 1",  # three-byte UTF-8, single UTF-16 unit
    ],
)
@pytest.mark.parametrize(
    "encoding",
    [
        PositionEncoding.UTF8_CODE_UNIT,
        PositionEncoding.UTF16_CODE_UNIT,
        PositionEncoding.UTF32_CODE_UNIT,
    ],
)
def test_column_conversion_round_trips_for_every_character(
    line_text: str, encoding: PositionEncoding
) -> None:
    for character in range(len(line_text) + 1):
        protocol = character_to_protocol(line_text, character, encoding)
        assert not protocol.ambiguous
        back = protocol_to_character(line_text, protocol.column, encoding)
        assert back.column == character, (line_text, encoding, character)
        assert not back.ambiguous


def test_a_column_inside_a_multi_unit_character_is_reported_as_ambiguous() -> None:
    """No character column represents the middle of a surrogate pair."""
    result = protocol_to_character(ROCKET_LINE, 1, PositionEncoding.UTF16_CODE_UNIT)
    assert result.column == 0
    assert result.ambiguous
    assert "multi-code-unit" in result.reason


def test_an_undeclared_encoding_only_matters_after_non_ascii() -> None:
    """Every encoding agrees on an ASCII prefix and disagrees after one."""
    assert not encoding_is_undecidable("value = 1", 6)
    assert not encoding_is_undecidable("🚀 Woo", 0)
    assert encoding_is_undecidable("🚀 Woo", 3)
    assert encoding_is_undecidable("سلام x", 5)


@pytest.mark.parametrize(
    ("tool", "version", "expected", "authoritative"),
    [
        # Measured from the committed real indexes, not assumed.
        ("scip-python", "0.6.6", PositionEncoding.UTF16_CODE_UNIT, True),
        ("scip-typescript", "0.4.0", PositionEncoding.UTF16_CODE_UNIT, True),
        # A version the measurement does not cover must not inherit its verdict.
        ("scip-python", "9.9.9", PositionEncoding.UTF32_CODE_UNIT, False),
        ("some-unknown-indexer", "1.0", PositionEncoding.UTF32_CODE_UNIT, False),
        ("", "", PositionEncoding.UTF32_CODE_UNIT, False),
    ],
)
def test_an_undeclared_encoding_falls_back_to_measured_tool_behaviour(
    tool: str, version: str, expected: PositionEncoding, authoritative: bool
) -> None:
    resolved = resolve_encoding(PositionEncoding.UNSPECIFIED, tool, version)
    assert resolved.encoding is expected
    assert resolved.authoritative is authoritative
    assert resolved.source is (
        EncodingSource.MEASURED if authoritative else EncodingSource.ASSUMED
    )


def test_a_declared_encoding_always_wins_over_the_compatibility_table() -> None:
    resolved = resolve_encoding(
        PositionEncoding.UTF8_CODE_UNIT, "scip-python", "0.6.6"
    )
    assert resolved.encoding is PositionEncoding.UTF8_CODE_UNIT
    assert resolved.source is EncodingSource.DECLARED
    assert resolved.authoritative


UNICODE_SYMBOL = symbol("app", "mod/`handler`.")


def _unicode_index(encoding: PositionEncoding, line_text: str) -> bytes:
    """Index ``handler`` where it really sits, in the indexer's own units."""
    character_start = line_text.index("handler")
    return (
        IndexBuilder()
        .add(
            Document(
                relative_path="mod.py",
                position_encoding=encoding,
                occurrences=(
                    Occurrence(
                        UNICODE_SYMBOL,
                        0,
                        column_in(line_text, character_start, encoding),
                        column_in(line_text, character_start + len("handler"), encoding),
                        roles=DEFINITION,
                    ),
                ),
                symbols=(SymbolInfo(UNICODE_SYMBOL, display_name="handler"),),
            )
        )
        .encode()
    )


@pytest.mark.parametrize(
    "encoding",
    [
        PositionEncoding.UTF8_CODE_UNIT,
        PositionEncoding.UTF16_CODE_UNIT,
        PositionEncoding.UTF32_CODE_UNIT,
    ],
)
@pytest.mark.parametrize(
    "line_text",
    [
        "def handler(): ...",
        "# 🚀 emoji before handler",
        "# سلام دنیا handler",
        "# 日本語 handler",
    ],
)
def test_caret_resolves_through_every_encoding(
    tmp_path: Path, encoding: PositionEncoding, line_text: str
) -> None:
    """One source position must resolve identically whatever unit the index used."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "mod.py").write_text(line_text + "\n", encoding="utf-8")
    index_path = root / "index.scip"
    index_path.write_bytes(_unicode_index(encoding, line_text))
    _freshen(root, index_path)

    provider = _provider(root)
    character_start = line_text.index("handler")
    # The caret is given in the public one-based character convention.
    bundle = provider.definition(PrecisionQuery("mod.py", 1, character_start + 1))
    assert [record.target_symbol for record in bundle.records] == [UNICODE_SYMBOL]

    record = bundle.records[0]
    assert record.exact
    assert record.trust is TrustTier.EXACT
    # Reported columns come back as character columns, not the indexer's units.
    assert record.start_column == character_start + 1
    assert record.end_column == character_start + len("handler") + 1


def test_a_caret_before_the_symbol_does_not_resolve(tmp_path: Path) -> None:
    """A wrong conversion would shift the caret onto the identifier."""
    line_text = "# 🚀 emoji before handler"
    root = tmp_path / "project"
    root.mkdir()
    (root / "mod.py").write_text(line_text + "\n", encoding="utf-8")
    index_path = root / "index.scip"
    index_path.write_bytes(_unicode_index(PositionEncoding.UTF16_CODE_UNIT, line_text))
    _freshen(root, index_path)
    provider = _provider(root)
    assert provider.definition(PrecisionQuery("mod.py", 1, 1)).records == []


def test_an_unconvertible_position_is_never_reported_as_exact(tmp_path: Path) -> None:
    """Without the source line the column cannot be trusted, so neither is the tier.

    A file above ``max_source_bytes`` is not read back, so its columns cannot
    be converted out of the indexer's units. The evidence is still useful — the
    symbol is right — but it is not exact, and it must not claim to be.
    """
    line_text = "def handler(): ..."
    root = tmp_path / "project"
    root.mkdir()
    (root / "mod.py").write_text(line_text + "\n", encoding="utf-8")
    index_path = root / "index.scip"
    index_path.write_bytes(_unicode_index(PositionEncoding.UTF16_CODE_UNIT, line_text))
    _freshen(root, index_path)

    assert _provider(root).evidence_for_symbol(
        UNICODE_SYMBOL, EvidenceKind.DEFINITION
    ).records[0].exact

    provider = _provider(root, max_source_bytes=1)
    record = provider.evidence_for_symbol(UNICODE_SYMBOL, EvidenceKind.DEFINITION).records[0]
    assert not record.exact
    assert not record.stale  # the index is fresh; only the position is uncertain
    assert record.trust is TrustTier.INFERRED_HIGH
    assert record.metadata["position_ambiguous"] is True
    assert "position encoding" in str(record.metadata["position_detail"])


# -- document-scoped local symbols -----------------------------------------

LOCAL = "local 1"
GLOBAL_A = symbol("app", "a/`run`().")
GLOBAL_B = symbol("app", "b/`run`().")


def _local_collision_index() -> bytes:
    """Two documents that each declare ``local 1``, as real indexers do."""
    return (
        IndexBuilder()
        .add(
            Document(
                relative_path="a.py",
                occurrences=(
                    Occurrence(LOCAL, 0, 4, 9, roles=DEFINITION),
                    Occurrence(LOCAL, 1, 10, 15),
                    Occurrence(GLOBAL_A, 3, 4, 7, roles=DEFINITION),
                ),
                symbols=(SymbolInfo(LOCAL, display_name="total"),),
            )
        )
        .add(
            Document(
                relative_path="b.py",
                occurrences=(
                    Occurrence(LOCAL, 0, 4, 8, roles=DEFINITION),
                    Occurrence(LOCAL, 2, 6, 10),
                    Occurrence(LOCAL, 5, 6, 10),
                    Occurrence(GLOBAL_B, 7, 4, 7, roles=DEFINITION),
                ),
                symbols=(SymbolInfo(LOCAL, display_name="count"),),
            )
        )
        .encode()
    )


def test_local_symbol_helpers_only_scope_locals() -> None:
    assert is_local_symbol("local 1")
    assert not is_local_symbol(GLOBAL_A)
    assert scoped_symbol_key("a.py", GLOBAL_A) == GLOBAL_A
    assert scoped_symbol_key("a.py", LOCAL) != scoped_symbol_key("b.py", LOCAL)


def test_local_symbols_do_not_collide_across_documents() -> None:
    index = import_index(_local_collision_index())
    a_occurrences = index.occurrences_for(LOCAL, "a.py")
    b_occurrences = index.occurrences_for(LOCAL, "b.py")

    assert {item.path for item in a_occurrences} == {"a.py"}
    assert {item.path for item in b_occurrences} == {"b.py"}
    assert len(a_occurrences) == 2
    assert len(b_occurrences) == 3
    assert len(index.references_for(LOCAL, "a.py")) == 1
    assert len(index.references_for(LOCAL, "b.py")) == 2


def test_a_local_symbol_without_a_document_resolves_to_nothing() -> None:
    """Returning the union of every same-named local would be worse than nothing."""
    index = import_index(_local_collision_index())
    assert index.occurrences_for(LOCAL) == ()
    assert index.definitions_for(LOCAL) == ()
    assert index.symbol_information(LOCAL) is None
    assert index.implementations_for(LOCAL) == ()


def test_global_symbols_still_resolve_without_a_document() -> None:
    """Scoping must not break the cross-file navigation that is the whole point."""
    index = import_index(_local_collision_index())
    assert len(index.definitions_for(GLOBAL_A)) == 1
    assert index.symbol_information(GLOBAL_A) is None  # declared without SymbolInfo
    assert len(index.occurrences_for(GLOBAL_B, "a.py")) == 1  # document is ignored


def test_local_symbol_metadata_is_document_scoped() -> None:
    index = import_index(_local_collision_index())
    a_info = index.symbol_information(LOCAL, "a.py")
    b_info = index.symbol_information(LOCAL, "b.py")
    assert a_info is not None and a_info.display_name == "total"
    assert b_info is not None and b_info.display_name == "count"


def test_navigation_from_a_caret_stays_inside_its_document(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("    total = 1\n    use(total)\n\ndef run(): ...\n", encoding="utf-8")
    (root / "b.py").write_text("    count = 2\n\n" + "\n" * 5 + "def run(): ...\n", encoding="utf-8")
    index_path = root / "index.scip"
    index_path.write_bytes(_local_collision_index())
    _freshen(root, index_path)
    provider = _provider(root)

    references = provider.references(PrecisionQuery("a.py", 1, 5))
    assert {record.path for record in references.records} == {"a.py"}
    assert len(references.records) == 1


def test_symbol_search_reports_each_document_that_declares_a_local() -> None:
    index = import_index(_local_collision_index())
    documents = {
        document.relative_path
        for document in index.documents
        for item in document.symbols
        if item.symbol == LOCAL
    }
    assert documents == {"a.py", "b.py"}


# -- project root -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("file:///workspace/app", "/workspace/app"),
        ("file:///home/user/my%20project", "/home/user/my project"),
        ("file:///C:/code/app", "C:/code/app"),
        ("file://localhost/workspace", "/workspace"),
        ("file://server/share/app", "//server/share/app"),
        ("/plain/absolute/path", "/plain/absolute/path"),
        ("", ""),
    ],
)
def test_project_root_is_decoded_as_a_uri(raw: str, expected: str) -> None:
    assert decode_project_root(raw) == expected


def test_an_index_project_root_never_redirects_file_access(tmp_path: Path) -> None:
    """The configured root is the trust boundary, not the one the index claims."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "mod.py").write_text("def handler(): ...\n", encoding="utf-8")
    builder = IndexBuilder(project_root="file:///etc")
    builder.add(
        Document(
            relative_path="mod.py",
            occurrences=(Occurrence(UNICODE_SYMBOL, 0, 4, 11, roles=DEFINITION),),
        )
    )
    index_path = root / "index.scip"
    index_path.write_bytes(builder.encode())
    _freshen(root, index_path)

    provider = _provider(root)
    index = provider.store.load()
    assert index is not None
    assert index.project_root == "/etc"  # reported...
    # ...but every resolved path stays under the configured root.
    bundle = provider.evidence_for_symbol(UNICODE_SYMBOL, EvidenceKind.DEFINITION)
    assert [record.path for record in bundle.records] == ["mod.py"]
    with pytest.raises(ValueError, match="inside the project root"):
        provider.store.relative_path("/etc/passwd")


# -- deterministic staleness ------------------------------------------------

LARGE_INDEX_DOCUMENTS = 600


def _large_index(count: int) -> bytes:
    builder = IndexBuilder()
    for number in range(count):
        name = f"src/mod_{number:04d}.py"
        item = symbol("app", f"mod{number}/`run`().")
        builder.add(
            Document(
                relative_path=name,
                occurrences=(Occurrence(item, 0, 4, 7, roles=DEFINITION),),
            )
        )
    return builder.encode()


def _large_project(tmp_path: Path, count: int) -> tuple[Path, Path]:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    for number in range(count):
        (root / "src" / f"mod_{number:04d}.py").write_text("def run(): ...\n", encoding="utf-8")
    index_path = root / "index.scip"
    index_path.write_bytes(_large_index(count))
    _freshen(root, index_path)
    return root, index_path


def test_staleness_detects_an_edit_beyond_any_sample_window(tmp_path: Path) -> None:
    """Document 500 of 600 must be checked, not sampled past.

    The previous implementation stat'd only the first 400 indexed documents and
    reported ``exact`` for everything after them, which is precisely the case
    where exactness is a false claim.
    """
    root, _ = _large_project(tmp_path, LARGE_INDEX_DOCUMENTS)
    store = PrecisionIndexStore(root=root)
    assert not store.status().stale

    later = time.time() + 600
    edited = root / "src" / "mod_0500.py"
    os.utime(edited, (later, later))

    status = store.status()
    assert status.stale
    assert "src/mod_0500.py" in status.stale_reason
    assert status.detail == "reindex to restore exact navigation"


def test_staleness_detects_a_deletion_beyond_any_sample_window(tmp_path: Path) -> None:
    root, _ = _large_project(tmp_path, LARGE_INDEX_DOCUMENTS)
    store = PrecisionIndexStore(root=root)
    assert not store.status().stale
    (root / "src" / "mod_0599.py").unlink()
    status = store.status()
    assert status.stale
    assert "src/mod_0599.py" in status.stale_reason


def test_a_stale_index_never_yields_exact_evidence(tmp_path: Path) -> None:
    root, _ = _large_project(tmp_path, LARGE_INDEX_DOCUMENTS)
    later = time.time() + 600
    os.utime(root / "src" / "mod_0500.py", (later, later))
    provider = _provider(root)
    bundle = provider.evidence_for_symbol(
        symbol("app", "mod0/`run`()."), EvidenceKind.DEFINITION
    )
    assert bundle.records
    for record in bundle.records:
        assert not record.exact
        assert record.stale
        assert record.trust is not TrustTier.EXACT


def test_a_staleness_reason_stays_bounded(tmp_path: Path) -> None:
    """Every stale document is detected; only the first few are named."""
    root, _ = _large_project(tmp_path, 20)
    later = time.time() + 600
    for number in range(20):
        os.utime(root / "src" / f"mod_{number:04d}.py", (later, later))
    reason = PrecisionIndexStore(root=root).status().stale_reason
    assert "and 17 more" in reason
    assert reason.count(".py") == 3


def test_an_explicit_freshness_ttl_reuses_a_verdict(tmp_path: Path) -> None:
    """The cache is opt-in, and its trade-off is that an edit inside it waits."""
    root, _ = _large_project(tmp_path, 12)
    store = PrecisionIndexStore(
        root=root, config=PrecisionIndexConfig(freshness_ttl_seconds=300.0)
    )
    assert not store.status().stale
    later = time.time() + 600
    os.utime(root / "src" / "mod_0000.py", (later, later))
    assert not store.status().stale  # still inside the configured window
    store.invalidate()
    assert store.status().stale


# -- helpers ----------------------------------------------------------------


def _freshen(root: Path, index_path: Path) -> None:
    """Make the index look newer than every source file it indexes."""
    later = time.time() + 60
    os.utime(index_path, (later, later))


def _provider(root: Path, **overrides: object) -> PrecisionEvidenceProvider:
    config = CortexConfig(project_root=root)
    if overrides:
        config = config.model_copy(
            update={"precision_index": PrecisionIndexConfig(**overrides)}  # type: ignore[arg-type]
        )
    return PrecisionEvidenceProvider(root, config)


def test_a_column_past_the_end_of_a_line_stays_past_the_end() -> None:
    """An end-exclusive boundary one past the last character must stay there.

    A range whose end sits at the line end is common, and clamping it into the
    line would silently shorten every such occurrence by one.
    """
    line = "🚀 ab"  # 4 characters, 7 UTF-8 bytes, 5 UTF-16 code units
    assert (len(line), len(line.encode("utf-8"))) == (4, 7)
    for encoding, total in (
        (PositionEncoding.UTF8_CODE_UNIT, 7),
        (PositionEncoding.UTF16_CODE_UNIT, 5),
    ):
        assert protocol_to_character(line, total, encoding).column == len(line)
        assert protocol_to_character(line, total + 3, encoding).column == len(line) + 3
        assert character_to_protocol(line, len(line), encoding).column == total
        assert character_to_protocol(line, len(line) + 3, encoding).column == total + 3


def test_a_negative_or_zero_column_converts_to_the_line_start() -> None:
    for encoding in (PositionEncoding.UTF8_CODE_UNIT, PositionEncoding.UTF16_CODE_UNIT):
        assert protocol_to_character("🚀 ab", 0, encoding).column == 0
        assert protocol_to_character("🚀 ab", -5, encoding).column == 0
        assert character_to_protocol("🚀 ab", 0, encoding).column == 0
        assert character_to_protocol("🚀 ab", -5, encoding).column == 0
