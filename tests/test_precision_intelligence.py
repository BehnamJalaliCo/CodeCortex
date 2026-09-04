from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from codecortex.config import CortexConfig, PrecisionIndexConfig
from codecortex.evidence import EvidenceKind, ProviderState, TrustTier
from codecortex.precision import (
    PrecisionEvidenceProvider,
    PrecisionIndexError,
    PrecisionIndexStore,
    PrecisionQuery,
    import_index,
    normalize_index_path,
    parse_symbol,
)
from codecortex.precision.identity import DescriptorKind, parse_descriptors
from codecortex.precision.wire import (
    WireFormatError,
    decode_message,
    encode_bytes_field,
    encode_string_field,
    encode_varint,
    encode_varint_field,
    read_varint,
)
from tests.fixtures.precision_index import (
    DEFINITION,
    Document,
    IndexBuilder,
    Occurrence,
    Relationship,
    SymbolInfo,
    symbol,
)

AUTH_SERVICE = symbol("app", "auth/`Service`#")
BILLING_SERVICE = symbol("app", "billing/`Service`#")
AUTH_RUN = symbol("app", "auth/`Service`#run().")
PROTOCOL = symbol("app", "core/`Runner`#")


def _duplicate_name_index() -> bytes:
    """Two packages export a class with the same display name."""
    return (
        IndexBuilder()
        .add(
            Document(
                relative_path="src/auth.py",
                occurrences=(
                    Occurrence(AUTH_SERVICE, 4, 6, 13, roles=DEFINITION),
                    Occurrence(PROTOCOL, 4, 14, 20),
                    Occurrence(AUTH_RUN, 5, 8, 11, roles=DEFINITION),
                ),
                symbols=(
                    SymbolInfo(
                        AUTH_SERVICE,
                        display_name="Service",
                        documentation=("Authentication service.",),
                        relationships=(Relationship(PROTOCOL, is_implementation=True),),
                    ),
                    SymbolInfo(AUTH_RUN, display_name="run"),
                ),
            )
        )
        .add(
            Document(
                relative_path="src/billing.py",
                occurrences=(Occurrence(BILLING_SERVICE, 2, 6, 13, roles=DEFINITION),),
                symbols=(SymbolInfo(BILLING_SERVICE, display_name="Service"),),
            )
        )
        .add(
            Document(
                relative_path="src/core.py",
                occurrences=(Occurrence(PROTOCOL, 0, 6, 12, roles=DEFINITION),),
                symbols=(SymbolInfo(PROTOCOL, display_name="Runner"),),
            )
        )
        .add(
            Document(
                relative_path="src/api.py",
                occurrences=(
                    Occurrence(AUTH_SERVICE, 9, 11, 18),
                    Occurrence(BILLING_SERVICE, 14, 4, 11),
                ),
            )
        )
        .encode()
    )


def _write_index(root: Path, payload: bytes, relative: str = ".codecortex/precision/index.cortexidx") -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "auth.py").write_text(
        "\n".join(
            [
                "from core import Runner",
                "",
                "",
                "",
                "class Service(Runner):",
                "    def run(self) -> int:",
                "        return 1",
            ]
        ),
        encoding="utf-8",
    )
    (root / "src" / "billing.py").write_text(
        "\n".join(["", "", "class Service:", "    pass"]), encoding="utf-8"
    )
    (root / "src" / "core.py").write_text("class Runner:\n    pass\n", encoding="utf-8")
    (root / "src" / "api.py").write_text(
        "\n".join(
            [
                "from auth import Service",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "def handle():",
                "    return Service().run()",
                "",
                "",
                "",
                "def bill():",
                "    return None",
            ]
        ),
        encoding="utf-8",
    )
    return root


def _provider(root: Path) -> PrecisionEvidenceProvider:
    config = CortexConfig(project_root=root)
    return PrecisionEvidenceProvider(root, config)


def _freshen(root: Path, index_path: Path) -> None:
    """Make the index newer than every source file it references."""
    future = time.time() + 60
    os.utime(index_path, (future, future))


# -- wire format ------------------------------------------------------------


def test_varint_round_trip_covers_multi_byte_values() -> None:
    for value in (0, 1, 127, 128, 300, 2**31, 2**63 - 1):
        decoded, offset = read_varint(encode_varint(value), 0)
        assert decoded == value
        assert offset == len(encode_varint(value))


def test_wire_reader_rejects_truncated_and_unknown_encodings() -> None:
    with pytest.raises(WireFormatError, match="truncated varint"):
        read_varint(b"\x80\x80", 0)
    with pytest.raises(WireFormatError, match="overruns"):
        decode_message(b"\x0a\x05ab")
    with pytest.raises(WireFormatError, match="unsupported wire type"):
        decode_message(b"\x0b")
    with pytest.raises(WireFormatError, match="field number 0"):
        decode_message(b"\x00\x01")


def test_wire_reader_skips_unknown_fields_and_reads_signed_values() -> None:
    payload = encode_varint_field(99, 7) + encode_string_field(1, "kept")
    message = decode_message(payload)
    assert message.text(1) == "kept"
    assert message.scalar(99) == 7
    assert message.text(1234, "fallback") == "fallback"
    assert message.int32s(5) == []


def test_wire_reader_rejects_deep_nesting() -> None:
    payload = encode_bytes_field(1, encode_bytes_field(1, b""))
    with pytest.raises(WireFormatError, match="too deep"):
        decode_message(payload, max_depth=1).message(1, max_depth=0)


# -- symbol identity --------------------------------------------------------


def test_symbol_identity_decomposes_package_and_descriptors() -> None:
    identity = parse_symbol(AUTH_RUN)
    assert identity.scheme == "index-python"
    assert identity.package_name == "app"
    assert identity.package_version == "1.0.0"
    assert identity.qualified_name == "auth.Service.run"
    assert identity.display_name == "run"
    assert identity.container == "auth.Service"
    assert identity.is_callable


def test_symbol_identity_handles_locals_escapes_and_malformed_input() -> None:
    local = parse_symbol("local 4")
    assert local.is_local and local.display_name == "4"

    escaped = parse_symbol("index-go gomod example  package 1.0 pkg/`My Type`#")
    assert escaped.package_name == "example package"
    assert escaped.display_name == "My Type"

    broken = parse_symbol("index-python pypi app 1.0 bad~suffix")
    assert broken.parse_error
    assert broken.display_name == broken.raw
    assert parse_symbol("").parse_error == "empty symbol"
    assert parse_symbol("too few fields").parse_error


def test_descriptor_parser_covers_every_suffix() -> None:
    kinds = [item.kind for item in parse_descriptors("ns/Type#term.meta:macro![T](arg)m().")]
    assert kinds == [
        DescriptorKind.NAMESPACE,
        DescriptorKind.TYPE,
        DescriptorKind.TERM,
        DescriptorKind.META,
        DescriptorKind.MACRO,
        DescriptorKind.TYPE_PARAMETER,
        DescriptorKind.PARAMETER,
        DescriptorKind.METHOD,
    ]
    for broken in ("[unclosed", "(unclosed", "name(", "", "`unterminated"):
        with pytest.raises(ValueError):
            parse_descriptors(broken)


# -- import -----------------------------------------------------------------


def test_import_reads_documents_symbols_and_occurrences() -> None:
    index = import_index(_duplicate_name_index())
    assert index.document_count == 4
    assert index.tool_name == "codecortex-test-indexer"
    assert index.occurrence_count == 7
    assert index.symbol_count == 4
    assert index.paths() == ("src/auth.py", "src/billing.py", "src/core.py", "src/api.py")
    assert index.document("src/auth.py") is not None
    assert index.document("missing.py") is None


def test_import_accepts_the_compact_range_encoding() -> None:
    payload = (
        IndexBuilder()
        .add(
            Document(
                relative_path="a.py",
                occurrences=(
                    Occurrence(AUTH_SERVICE, 1, 2, 9, roles=DEFINITION, typed_range=False),
                    Occurrence(AUTH_RUN, 3, 1, 4, end_line=5, typed_range=False),
                ),
            )
        )
        .encode()
    )
    index = import_index(payload)
    first, second = index.document("a.py").occurrences
    assert (first.range.start_line, first.range.end_line) == (1, 1)
    assert (second.range.start_line, second.range.end_line) == (3, 5)


def test_import_rejects_malformed_and_unsupported_indexes() -> None:
    with pytest.raises(PrecisionIndexError, match="empty"):
        import_index(b"")
    with pytest.raises(PrecisionIndexError, match="malformed"):
        import_index(b"\x0b\x0b\x0b")
    with pytest.raises(PrecisionIndexError, match="no documents"):
        import_index(IndexBuilder().encode())
    with pytest.raises(PrecisionIndexError, match="unsupported precision index schema"):
        import_index(IndexBuilder(protocol_version=99).add(Document("a.py")).encode())
    bad_range = encode_bytes_field(
        1, encode_varint_field(1, 0)
    ) + encode_bytes_field(
        2,
        encode_string_field(1, "a.py")
        + encode_bytes_field(
            2,
            encode_string_field(2, AUTH_SERVICE)
            + encode_bytes_field(1, encode_varint(1) + encode_varint(2)),
        ),
    )
    with pytest.raises(PrecisionIndexError, match="three or four"):
        import_index(bad_range)


def test_path_normalization_accepts_windows_separators() -> None:
    """Windows separators are a spelling difference, not a schema violation."""
    assert normalize_index_path("src\\pkg\\mod.py") == "src/pkg/mod.py"
    assert normalize_index_path("src/pkg/mod.py") == "src/pkg/mod.py"


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("/etc/passwd", "must not begin with a separator"),
        ("/src/a.py", "must not begin with a separator"),
        ("C:\\outside\\file.py", "not absolute"),
        ("c:/outside/file.py", "not absolute"),
        ("../outside.py", "not canonical"),
        ("a/../outside.py", "not canonical"),
        ("./src/a.py", "not canonical"),
        ("a/./b.py", "not canonical"),
        ("a//b.py", "empty component"),
        ("file:///etc/passwd", "not a URI"),
        ("https://example.test/a.py", "not a URI"),
        ("a\x00b.py", "NUL byte"),
        ("", "missing its relative path"),
        ("   ", "missing its relative path"),
    ],
)
def test_invalid_document_paths_are_rejected_not_repaired(path: str, reason: str) -> None:
    """A schema-violating path must fail, not be rewritten into a plausible one.

    Stripping the leading separator off ``/etc/passwd`` yields ``etc/passwd``,
    which looks like an ordinary repository path and would then be joined to
    the project root and read.
    """
    with pytest.raises(PrecisionIndexError, match=reason):
        normalize_index_path(path)


def test_import_skips_documents_missing_a_path() -> None:
    payload = encode_bytes_field(1, encode_varint_field(1, 0)) + encode_bytes_field(
        2, encode_string_field(4, "Python")
    )
    with pytest.raises(PrecisionIndexError, match="missing its relative path"):
        import_index(payload)


# -- store, discovery, staleness -------------------------------------------


def test_store_discovers_default_locations_and_reports_status(tmp_path: Path) -> None:
    root = _project(tmp_path)
    store = PrecisionIndexStore(root=root)
    assert store.status().label == "unavailable"
    index_path = _write_index(root, _duplicate_name_index(), "index.cortexidx")
    _freshen(root, index_path)
    status = store.status()
    assert status.label == "available"
    assert status.documents == 4
    assert status.path == str(index_path)
    assert status.to_dict()["indexer"].startswith("codecortex-test-indexer")


def test_store_honours_an_explicit_configured_path(tmp_path: Path) -> None:
    root = _project(tmp_path)
    index_path = _write_index(root, _duplicate_name_index(), "custom/my.index")
    _freshen(root, index_path)
    store = PrecisionIndexStore(
        root=root, config=PrecisionIndexConfig(path="custom/my.index")
    )
    assert store.candidate_paths() == (index_path,)
    assert store.status().available


def test_store_reports_disabled_missing_oversized_and_malformed_indexes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    disabled = PrecisionIndexStore(root=root, config=PrecisionIndexConfig(enabled=False))
    assert disabled.status().label == "disabled"
    assert disabled.load() is None

    _write_index(root, b"\x0b\x0b\x0b")
    broken = PrecisionIndexStore(root=root).status()
    assert broken.label == "unavailable" and "malformed" in broken.detail

    _write_index(root, _duplicate_name_index())
    oversized = PrecisionIndexStore(
        root=root, config=PrecisionIndexConfig(max_index_bytes=8)
    ).status()
    assert oversized.label == "unavailable" and "exceeds the configured limit" in oversized.detail


def test_store_detects_a_stale_index_after_a_source_edit(tmp_path: Path) -> None:
    root = _project(tmp_path)
    index_path = _write_index(root, _duplicate_name_index())
    _freshen(root, index_path)
    store = PrecisionIndexStore(root=root)
    assert not store.status().stale

    later = time.time() + 600
    os.utime(root / "src" / "auth.py", (later, later))
    status = store.status()
    assert status.stale and "src/auth.py" in status.stale_reason
    assert status.label == "stale"


def test_store_detects_indexed_files_that_no_longer_exist(tmp_path: Path) -> None:
    root = _project(tmp_path)
    index_path = _write_index(root, _duplicate_name_index())
    _freshen(root, index_path)
    (root / "src" / "billing.py").unlink()
    status = PrecisionIndexStore(root=root).status()
    assert status.stale and "missing" in status.stale_reason


def test_store_caches_by_fingerprint_and_invalidates_on_demand(tmp_path: Path) -> None:
    root = _project(tmp_path)
    index_path = _write_index(root, _duplicate_name_index())
    _freshen(root, index_path)
    store = PrecisionIndexStore(root=root)
    first = store.load()
    assert first is not None and store.load() is first
    store.invalidate()
    assert store.load() is not first


def test_store_rejects_paths_outside_the_project_root(tmp_path: Path) -> None:
    root = _project(tmp_path)
    store = PrecisionIndexStore(root=root)
    assert store.relative_path("src/auth.py") == "src/auth.py"
    with pytest.raises(ValueError, match="inside the project root"):
        store.relative_path("../escape.py")


# -- provider ---------------------------------------------------------------


def test_precise_definition_distinguishes_duplicate_symbol_names(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _freshen(root, _write_index(root, _duplicate_name_index()))
    provider = _provider(root)

    auth = provider.definition(PrecisionQuery("src/api.py", 10, 12))
    assert [record.path for record in auth.records] == ["src/auth.py"]
    assert auth.records[0].start_line == 5
    assert auth.records[0].exact and auth.records[0].trust is TrustTier.EXACT
    assert not auth.degraded

    billing = provider.definition(PrecisionQuery("src/api.py", 15, 5))
    assert [record.path for record in billing.records] == ["src/billing.py"]
    assert billing.records[0].start_line == 3


def test_precise_references_and_implementations(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _freshen(root, _write_index(root, _duplicate_name_index()))
    provider = _provider(root)

    references = provider.references(PrecisionQuery("src/auth.py", 5, 7))
    assert [(item.path, item.start_line) for item in references.records] == [("src/api.py", 10)]
    assert references.records[0].kind is EvidenceKind.REFERENCE

    implementations = provider.implementations(PrecisionQuery("src/auth.py", 5, 15))
    assert [(item.path, item.start_line) for item in implementations.records] == [
        ("src/auth.py", 5)
    ]
    assert implementations.records[0].kind is EvidenceKind.IMPLEMENTATION
    assert provider.implementations(PrecisionQuery("src/billing.py", 3, 7)).records == []


def test_provider_reports_missing_index_and_unmatched_positions(tmp_path: Path) -> None:
    root = _project(tmp_path)
    provider = _provider(root)
    missing = provider.definition(PrecisionQuery("src/api.py", 10, 12))
    assert missing.records == []
    report = missing.report_for("precision_index")
    assert report is not None and report.state is ProviderState.UNAVAILABLE
    assert report.fallback

    _freshen(root, _write_index(root, _duplicate_name_index()))
    provider = _provider(root)
    nothing = provider.definition(PrecisionQuery("src/api.py", 1, 1))
    assert nothing.records == []
    assert "no indexed symbol" in (nothing.report_for("precision_index") or report).detail


def test_stale_index_is_never_reported_as_exact(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _freshen(root, _write_index(root, _duplicate_name_index()))
    later = time.time() + 600
    os.utime(root / "src" / "api.py", (later, later))
    provider = _provider(root)

    bundle = provider.definition(PrecisionQuery("src/api.py", 10, 12))
    assert bundle.records
    record = bundle.records[0]
    assert record.stale and not record.exact
    assert record.trust is TrustTier.INFERRED_HIGH
    assert bundle.exact == []
    assert bundle.degraded
    assert (bundle.report_for("precision_index") or record).state is ProviderState.STALE


def test_symbol_lookup_occurrences_and_search(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _freshen(root, _write_index(root, _duplicate_name_index()))
    provider = _provider(root)

    resolved = provider.symbol_at(PrecisionQuery("src/api.py", 10, 12))
    assert resolved["symbol"]["qualified_name"] == "auth.Service"
    assert resolved["symbol"]["documentation"] == ["Authentication service."]

    occurrences = provider.occurrences(AUTH_SERVICE)
    assert [item.path for item in occurrences.records] == ["src/api.py"]

    assert {item["qualified_name"] for item in provider.search_symbols("service")} == {
        "auth.Service",
        "auth.Service.run",
        "billing.Service",
    }
    assert provider.search_symbols("   ") == []
    assert len(provider.search_symbols("service", limit=1)) == 1


@pytest.mark.asyncio
async def test_provider_collect_and_health(tmp_path: Path) -> None:
    from codecortex.evidence import EvidenceRequest

    root = _project(tmp_path)
    provider = _provider(root)
    assert await provider.health() is False
    empty = await provider.collect(EvidenceRequest(query="anything"))
    assert empty.records == []

    _freshen(root, _write_index(root, _duplicate_name_index()))
    provider = _provider(root)
    assert await provider.health() is True

    positional = await provider.collect(
        EvidenceRequest(query="who calls Service", path="src/api.py", line=10, column=12)
    )
    assert {record.kind for record in positional.records} == {
        EvidenceKind.DEFINITION,
        EvidenceKind.REFERENCE,
    }

    by_symbol = await provider.collect(EvidenceRequest(query="usages", symbol=AUTH_SERVICE))
    assert [record.path for record in by_symbol.records] == ["src/api.py"]
