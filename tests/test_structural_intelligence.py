from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from codecortex.config import CortexConfig, StructuralConfig
from codecortex.evidence import EvidenceKind, EvidenceRequest, ProviderState, TrustTier
from codecortex.structural import (
    RewriteRejected,
    StructuralEngine,
    StructuralEngineUnavailable,
    StructuralError,
    StructuralEvidenceProvider,
    StructuralRewriteService,
    StructuralSearch,
    contain_path,
)
from codecortex.structural.rewrite import RewriteStore

FAKE_ENGINE = Path(__file__).parent / "fixtures" / "structural_engine.py"


def _fake_prefix() -> tuple[str, ...]:
    return (sys.executable, str(FAKE_ENGINE))


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "handlers.py").write_text(
        "def handler():\n    return old_api(1)\n\n\ndef other():\n    return old_api(2)\n",
        encoding="utf-8",
    )
    (root / "src" / "helpers.py").write_text(
        "def helper():\n    return old_api(3)\n", encoding="utf-8"
    )
    (root / "src" / "clean.py").write_text("def clean():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "CodeCortex CI"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
    return root


def _config(root: Path, **overrides: object) -> CortexConfig:
    return CortexConfig(project_root=root, structural=StructuralConfig(**overrides))


def _search(root: Path, **overrides: object) -> StructuralSearch:
    config = _config(root, **overrides)
    engine = StructuralEngine(root, config.structural, argv_prefix=_fake_prefix())
    return StructuralSearch(root, config, engine)


def _service(root: Path, **overrides: object) -> StructuralRewriteService:
    config = _config(root, **overrides)
    engine = StructuralEngine(root, config.structural, argv_prefix=_fake_prefix())
    return StructuralRewriteService(root, config, StructuralSearch(root, config, engine))


# -- engine discovery -------------------------------------------------------


def test_engine_reports_missing_and_disabled_states(tmp_path: Path) -> None:
    root = _project(tmp_path)
    disabled = StructuralEngine(root, StructuralConfig(enabled=False))
    status = disabled.status()
    assert not status.available and "disabled" in status.detail
    with pytest.raises(StructuralEngineUnavailable, match="disabled"):
        disabled.argv_prefix()

    missing = StructuralEngine(root, StructuralConfig(command="codecortex-no-such-engine"))
    assert "not found on PATH" in missing.status().detail

    absent_path = StructuralEngine(
        root, StructuralConfig(command=str(tmp_path / "nowhere" / "engine"))
    )
    assert "not found" in absent_path.status().detail


def test_engine_resolves_a_configured_absolute_path(tmp_path: Path) -> None:
    root = _project(tmp_path)
    engine = StructuralEngine(
        root,
        StructuralConfig(command=sys.executable, command_args=(str(FAKE_ENGINE),)),
    )
    status = engine.status()
    assert status.available
    assert status.version.startswith("fake-structural-engine")
    assert status.to_dict()["status"] == "available"


def test_engine_rejects_empty_patterns_and_languages(tmp_path: Path) -> None:
    root = _project(tmp_path)
    engine = StructuralEngine(root, StructuralConfig(), argv_prefix=_fake_prefix())
    with pytest.raises(StructuralError, match="pattern must not be empty"):
        list(engine.search(pattern="  ", language="python"))
    with pytest.raises(StructuralError, match="requires a language"):
        list(engine.search(pattern="x", language=""))


def test_engine_surfaces_real_failures_and_malformed_output(tmp_path: Path) -> None:
    root = _project(tmp_path)
    engine = StructuralEngine(root, StructuralConfig(), argv_prefix=_fake_prefix())
    with pytest.raises(StructuralError, match="exit 2"):
        list(engine.search(pattern="((((", language="python"))
    with pytest.raises(StructuralError, match="unsupported language"):
        list(engine.search(pattern="x", language="unsupported-language"))
    with pytest.raises(StructuralError, match="malformed output"):
        list(engine.search(pattern="__emit_garbage__", language="python"))


def test_engine_timeout_is_bounded(tmp_path: Path) -> None:
    root = _project(tmp_path)
    sleeper = tmp_path / "sleeper.py"
    sleeper.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    engine = StructuralEngine(
        root,
        StructuralConfig(timeout_seconds=0.5),
        argv_prefix=(sys.executable, str(sleeper)),
    )
    with pytest.raises(StructuralError, match="timed out"):
        list(engine.search(pattern="x", language="python"))


# -- search -----------------------------------------------------------------


def test_structural_search_returns_typed_matches_with_captures(tmp_path: Path) -> None:
    root = _project(tmp_path)
    matches = _search(root).search("old_api", "python")
    assert [(item.path, item.start_line) for item in matches] == [
        ("src/handlers.py", 2),
        ("src/handlers.py", 6),
        ("src/helpers.py", 2),
    ]
    first = matches[0]
    assert first.start_column == 12
    assert first.captures == {"NAME": "old_api"}
    assert first.language == "Python"
    assert first.byte_length == len("old_api")


def test_structural_search_scopes_excludes_and_limits(tmp_path: Path) -> None:
    root = _project(tmp_path)
    scoped = _search(root).search("old_api", "python", paths=("src/helpers.py",))
    assert {item.path for item in scoped} == {"src/handlers.py", "src/helpers.py"}

    excluded = _search(root).search("old_api", "python", exclude=("src/helpers.py",))
    assert {item.path for item in excluded} == {"src/handlers.py"}

    limited = _search(root).search("old_api", "python", limit=1)
    assert len(limited) == 1

    capped = _search(root, max_results=2).search("old_api", "python")
    assert len(capped) == 2


def test_structural_search_rejects_paths_outside_the_project(tmp_path: Path) -> None:
    root = _project(tmp_path)
    search = _search(root)
    with pytest.raises(StructuralError, match="escapes the project root"):
        search.search("old_api", "python", paths=("../",))
    with pytest.raises(StructuralError, match="does not exist"):
        search.search("old_api", "python", paths=("src/missing.py",))


def test_structural_search_drops_matches_reported_outside_the_project(tmp_path: Path) -> None:
    root = _project(tmp_path)
    assert _search(root).search("__emit_outside__", "python") == []


def test_path_containment_rejects_symlink_escapes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    link = root / "link.py"
    try:
        link.symlink_to(outside)
    except OSError:  # pragma: no cover - platform dependent
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(StructuralError, match="escapes the project root"):
        contain_path(root, "link.py")
    with pytest.raises(StructuralError, match="escapes the project root"):
        contain_path(root, str(outside))


# -- preview ----------------------------------------------------------------


def test_rewrite_preview_plans_without_touching_source(tmp_path: Path) -> None:
    root = _project(tmp_path)
    before = (root / "src" / "handlers.py").read_text(encoding="utf-8")
    preview = _service(root).preview("old_api", "new_api", "python")

    assert (root / "src" / "handlers.py").read_text(encoding="utf-8") == before
    assert preview.total_matches == 3
    assert {item.path for item in preview.files} == {"src/handlers.py", "src/helpers.py"}
    assert all(item.original_sha256 for item in preview.files)
    assert "new_api" in preview.files[0].diff
    assert not preview.expired
    assert 0.0 <= preview.risk_score <= 1.0
    assert "handler" in preview.affected_symbols


def test_rewrite_preview_rejects_empty_replacements_and_no_matches(tmp_path: Path) -> None:
    root = _project(tmp_path)
    service = _service(root)
    with pytest.raises(StructuralError, match="requires a replacement"):
        service.preview("old_api", "   ", "python")
    with pytest.raises(RewriteRejected, match="matched nothing"):
        service.preview("absent_symbol_xyz", "new_api", "python")


def test_rewrite_preview_enforces_file_match_and_byte_limits(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with pytest.raises(RewriteRejected, match="spans 2 files"):
        _service(root, max_rewrite_files=1).preview("old_api", "new_api", "python")
    with pytest.raises(RewriteRejected, match="3 matches"):
        _service(root, max_rewrite_matches=2).preview("old_api", "new_api", "python")
    with pytest.raises(RewriteRejected, match="above the configured limit"):
        _service(root, max_rewrite_bytes=1).preview("old_api", "much_longer_new_api", "python")


def test_rewrite_preview_warns_when_a_replacement_changes_nothing(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with pytest.raises(RewriteRejected, match="no file could be rewritten"):
        _service(root).preview("old_api", "old_api", "python")


# -- apply ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rewrite_apply_requires_a_valid_preview(tmp_path: Path) -> None:
    root = _project(tmp_path)
    service = _service(root)
    with pytest.raises(RewriteRejected, match="unknown rewrite preview"):
        await service.apply("0" * 32)
    for bad in ("", "../escape", "a.b", "x" * 65):
        with pytest.raises(RewriteRejected, match="invalid preview id"):
            await service.apply(bad)


@pytest.mark.asyncio
async def test_rewrite_apply_writes_reindexes_and_validates(tmp_path: Path) -> None:
    root = _project(tmp_path)
    service = _service(root)
    preview = service.preview("old_api", "new_api", "python")
    result = await service.apply(preview.preview_id)

    assert result.applied and result.files_changed == 2 and result.matches_applied == 3
    assert "new_api" in (root / "src" / "handlers.py").read_text(encoding="utf-8")
    assert "old_api" not in (root / "src" / "helpers.py").read_text(encoding="utf-8")
    assert result.validation["passed"] is True
    assert result.validation["checked"] >= 3
    assert "residual_risk" in result.post_impact
    assert all(item.applied for item in result.files)

    with pytest.raises(RewriteRejected, match="unknown rewrite preview"):
        await service.apply(preview.preview_id)


@pytest.mark.asyncio
async def test_rewrite_apply_refuses_a_file_changed_after_the_preview(tmp_path: Path) -> None:
    root = _project(tmp_path)
    service = _service(root)
    preview = service.preview("old_api", "new_api", "python")
    (root / "src" / "helpers.py").write_text("def helper():\n    return 0\n", encoding="utf-8")

    with pytest.raises(RewriteRejected, match="changed after the preview"):
        await service.apply(preview.preview_id)
    assert "old_api" in (root / "src" / "handlers.py").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_rewrite_apply_refuses_a_deleted_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    service = _service(root)
    preview = service.preview("old_api", "new_api", "python")
    (root / "src" / "helpers.py").unlink()
    with pytest.raises(RewriteRejected, match="disappeared after the preview"):
        await service.apply(preview.preview_id)


@pytest.mark.asyncio
async def test_rewrite_apply_refuses_expired_previews(tmp_path: Path) -> None:
    root = _project(tmp_path)
    service = _service(root, preview_ttl_seconds=1)
    preview = service.preview("old_api", "new_api", "python")
    stored = service.store.load(preview.preview_id)
    expired = preview.model_copy(update={"expires_at": preview.created_at})
    service.store.save(expired, stored[1])
    with pytest.raises(RewriteRejected, match="expired"):
        await service.apply(preview.preview_id)


@pytest.mark.asyncio
async def test_rewrite_apply_is_blocked_by_policy_and_configuration(tmp_path: Path) -> None:
    root = _project(tmp_path)
    service = _service(root)
    preview = service.preview("old_api", "new_api", "python")
    with pytest.raises(RewriteRejected, match="not authorized"):
        await service.apply(preview.preview_id, authorized=False)

    blocked = _service(root, allow_apply=False)
    with pytest.raises(RewriteRejected, match="disabled in configuration"):
        await blocked.apply(preview.preview_id)
    assert "old_api" in (root / "src" / "handlers.py").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_rewrite_rolls_back_when_a_write_fails(tmp_path: Path) -> None:
    root = _project(tmp_path)
    service = _service(root)
    preview = service.preview("old_api", "new_api", "python")
    original = (root / "src" / "handlers.py").read_bytes()

    calls: list[Path] = []
    real_write = StructuralRewriteService._atomic_write

    def failing(target: Path, payload: bytes) -> None:
        calls.append(target)
        if len(calls) > 1:
            raise OSError(28, "No space left on device")
        real_write(target, payload)

    service._atomic_write = staticmethod(failing)  # type: ignore[method-assign]
    result = await service.apply(preview.preview_id)

    assert not result.applied and result.rolled_back
    assert (root / "src" / "handlers.py").read_bytes() == original
    assert any(not item.applied and item.reason for item in result.files)
    assert "rolled back" in result.detail


def test_rewrite_store_rejects_corrupt_previews(tmp_path: Path) -> None:
    store = RewriteStore(tmp_path / "rewrites")
    store._path("abc").parent.mkdir(parents=True, exist_ok=True)
    store._path("abc").write_text('{"preview": {"bad": true}}', encoding="utf-8")
    with pytest.raises(RewriteRejected, match="corrupt rewrite preview"):
        store.load("abc")
    store.discard("abc")
    store.discard("never-existed")


def test_rewrite_preview_payload_is_json_serializable(tmp_path: Path) -> None:
    root = _project(tmp_path)
    service = _service(root)
    preview = service.preview("old_api", "new_api", "python")
    payload = service.preview_payload(preview)
    assert payload["preview_id"] == preview.preview_id
    assert isinstance(payload["expires_at"], str)
    assert service.load_preview(preview.preview_id).pattern == "old_api"


def test_rewrite_apply_sync_wrapper(tmp_path: Path) -> None:
    root = _project(tmp_path)
    service = _service(root)
    preview = service.preview("old_api", "new_api", "python")
    assert service.apply_sync(preview.preview_id).applied


# -- evidence provider ------------------------------------------------------


@pytest.mark.asyncio
async def test_structural_evidence_provider_reports_matches_and_failures(tmp_path: Path) -> None:
    root = _project(tmp_path)
    provider = StructuralEvidenceProvider(root, _config(root), _search(root))
    assert await provider.health() is True

    bundle = await provider.collect(
        EvidenceRequest(
            query="find the old API",
            metadata={"structural_pattern": "old_api", "structural_language": "python"},
        )
    )
    assert len(bundle.records) == 3
    assert bundle.records[0].kind is EvidenceKind.STRUCTURAL_MATCH
    assert bundle.records[0].trust is TrustTier.STRUCTURAL
    assert bundle.records[0].exact is False

    without_pattern = await provider.collect(EvidenceRequest(query="anything"))
    assert without_pattern.records == []
    assert (
        without_pattern.report_for("structural") or bundle.providers[0]
    ).state is ProviderState.NOT_CONFIGURED

    failing = await provider.collect(
        EvidenceRequest(
            query="broken",
            metadata={"structural_pattern": "((((", "structural_language": "python"},
        )
    )
    assert failing.records == []
    report = failing.report_for("structural")
    assert report is not None and report.state is ProviderState.UNAVAILABLE
    assert report.fallback == "lexical and symbol search"


@pytest.mark.asyncio
async def test_structural_provider_is_unavailable_without_an_engine(tmp_path: Path) -> None:
    root = _project(tmp_path)
    config = _config(root, command="codecortex-no-such-engine")
    provider = StructuralEvidenceProvider(root, config)
    assert await provider.health() is False


