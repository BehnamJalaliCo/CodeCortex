from __future__ import annotations

import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from codecortex.config import CortexConfig, DependencyDocsConfig
from codecortex.dependencies import (
    DependencyDocumentationProvider,
    DependencyEvidenceProvider,
    DependencyIntelligence,
    DependencyResolver,
    DocumentationCache,
    DocumentationEvidence,
    DocumentationUnavailable,
    Ecosystem,
    LibraryResolution,
    ManifestScanner,
    RemoteDocumentationProvider,
    redact_secrets,
)
from codecortex.dependencies.models import DependencyScope
from codecortex.evidence import EvidenceKind, EvidenceRequest, ProviderState, TrustTier

API_KEY_ENV = "CODECORTEX_DEPENDENCY_DOCS_API_KEY"


# -- fakes ------------------------------------------------------------------


class FakeDocumentationProvider(DependencyDocumentationProvider):
    """Deterministic provider; no network and no credentials required."""

    key = "fake_docs"

    def __init__(
        self,
        *,
        failure: DocumentationUnavailable | None = None,
        docs: list[DocumentationEvidence] | None = None,
    ) -> None:
        self.failure = failure
        self.docs = docs
        self.calls: list[tuple[str, str, str | None]] = []

    async def health(self) -> bool:
        return self.failure is None

    async def resolve_library(
        self, name: str, query: str, version: str | None
    ) -> LibraryResolution:
        self.calls.append(("resolve", name, version))
        if self.failure is not None:
            raise self.failure
        return LibraryResolution(
            library_id=f"/{name}", title=name, versions=(version or "0",), provider=self.key
        )

    async def query_docs(
        self, library_id: str, query: str, version: str | None
    ) -> list[DocumentationEvidence]:
        self.calls.append(("docs", library_id, version))
        if self.failure is not None:
            raise self.failure
        if self.docs is not None:
            return self.docs
        return [
            DocumentationEvidence(
                library_id=library_id,
                content=f"{library_id}@{version}: middleware API",
                version=version,
                provider=self.key,
            )
        ]


class _StubHandler(BaseHTTPRequestHandler):
    routes: dict[str, tuple[int, str, str]] = {}
    seen: list[tuple[str, dict[str, str]]] = []
    bodies: list[str] = []

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        path, _, query = self.path.partition("?")
        _StubHandler.seen.append((path, dict(self.headers)))
        _StubHandler.bodies.append(query)
        status, content_type, body = _StubHandler.routes.get(
            path, (404, "application/json", '{"message":"missing"}')
        )
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: Any) -> None:  # pragma: no cover - silence test output
        return


class _StubServer:
    def __init__(self, routes: dict[str, tuple[int, str, str]]) -> None:
        _StubHandler.routes = routes
        _StubHandler.seen = []
        _StubHandler.bodies = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> _StubServer:
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}/api"


# -- manifest discovery -----------------------------------------------------


def _python_project(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "demo"',
                'dependencies = ["httpx>=0.27,<1", "pydantic[email] >=2.8 ; python_version>=\'3.11\'"]',
                "[project.optional-dependencies]",
                'dev = ["pytest>=8"]',
                "[tool.poetry.dependencies]",
                'python = "^3.11"',
                'rich = { version = "^13.7" }',
            ]
        ),
        encoding="utf-8",
    )
    (root / "requirements").mkdir(exist_ok=True)
    (root / "requirements" / "dev.txt").write_text(
        "# comment\n-r base.txt\nruff==0.16.5\n\n", encoding="utf-8"
    )
    (root / "uv.lock").write_text(
        '[[package]]\nname = "httpx"\nversion = "0.27.2"\n\n'
        '[[package]]\nname = "pydantic"\nversion = "2.9.1"\n',
        encoding="utf-8",
    )


def test_python_manifests_declare_and_lockfiles_resolve(tmp_path: Path) -> None:
    _python_project(tmp_path / "proj")
    inventory = DependencyResolver(tmp_path / "proj").inventory()
    httpx = inventory.find("httpx")[0]
    assert httpx.declared == ">=0.27,<1"
    assert httpx.resolved == "0.27.2"
    assert httpx.effective_version == "0.27.2"
    assert httpx.lock_source == "uv.lock"

    pydantic = inventory.find("pydantic")[0]
    assert pydantic.declared == ">=2.8"

    assert inventory.find("pytest")[0].scope is DependencyScope.DEVELOPMENT
    assert inventory.find("ruff")[0].declared == "==0.16.5"
    assert inventory.find("rich")[0].declared == "^13.7"
    assert inventory.find("python") == ()


def test_node_manifests_distinguish_declared_from_resolved(tmp_path: Path) -> None:
    root = tmp_path / "node"
    root.mkdir()
    (root / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"next": "^15.0.0", "@scope/ui": "1.x"},
                "devDependencies": {"vitest": "^2"},
            }
        ),
        encoding="utf-8",
    )
    (root / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "": {"name": "root"},
                    "node_modules/next": {"version": "15.4.3"},
                    "node_modules/@scope/ui": {"version": "1.2.0"},
                }
            }
        ),
        encoding="utf-8",
    )
    inventory = DependencyResolver(root).inventory()
    nxt = inventory.find("next")[0]
    assert (nxt.declared, nxt.resolved) == ("^15.0.0", "15.4.3")
    assert inventory.find("@scope/ui")[0].resolved == "1.2.0"
    assert inventory.find("vitest")[0].scope is DependencyScope.DEVELOPMENT


def test_legacy_node_lock_and_yarn_and_pnpm_formats(tmp_path: Path) -> None:
    root = tmp_path / "locks"
    root.mkdir()
    (root / "package-lock.json").write_text(
        json.dumps({"dependencies": {"left-pad": {"version": "1.3.0"}}}), encoding="utf-8"
    )
    (root / "yarn.lock").write_text(
        '"react@^18.0.0":\n  version "18.3.1"\n  resolved "https://example.invalid"\n',
        encoding="utf-8",
    )
    (root / "pnpm-lock.yaml").write_text(
        "lockfileVersion: '9.0'\npackages:\n  typescript:\n    version: 5.6.2\n",
        encoding="utf-8",
    )
    inventory = DependencyResolver(root).inventory()
    assert inventory.find("left-pad")[0].resolved == "1.3.0"
    assert inventory.find("react")[0].resolved == "18.3.1"
    assert inventory.find("typescript")[0].resolved == "5.6.2"


def test_rust_go_jvm_and_dotnet_manifests(tmp_path: Path) -> None:
    root = tmp_path / "poly"
    root.mkdir()
    (root / "Cargo.toml").write_text(
        '[dependencies]\nserde = "1.0"\ntokio = { version = "1.40", features = ["full"] }\n'
        '[dev-dependencies]\ncriterion = "0.5"\n',
        encoding="utf-8",
    )
    (root / "Cargo.lock").write_text(
        '[[package]]\nname = "serde"\nversion = "1.0.210"\n', encoding="utf-8"
    )
    (root / "go.mod").write_text(
        "module example.com/app\n\ngo 1.23\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.10.0\n)\n",
        encoding="utf-8",
    )
    (root / "go.sum").write_text(
        "github.com/gin-gonic/gin v1.10.0 h1:abc=\n"
        "github.com/gin-gonic/gin v1.10.0/go.mod h1:def=\n",
        encoding="utf-8",
    )
    (root / "pom.xml").write_text(
        "<project><properties><spring.version>6.1.5</spring.version></properties>"
        "<dependencies><dependency><groupId>org.springframework</groupId>"
        "<artifactId>spring-core</artifactId><version>${spring.version}</version></dependency>"
        "<dependency><groupId>junit</groupId><artifactId>junit</artifactId>"
        "<version>4.13.2</version><scope>test</scope></dependency></dependencies></project>",
        encoding="utf-8",
    )
    (root / "build.gradle.kts").write_text(
        'dependencies {\n  implementation("com.squareup.okhttp3:okhttp:4.12.0")\n}\n',
        encoding="utf-8",
    )
    (root / "app.csproj").write_text(
        '<Project><ItemGroup><PackageReference Include="Serilog" Version="4.0.1" />'
        "</ItemGroup></Project>",
        encoding="utf-8",
    )
    (root / "packages.lock.json").write_text(
        json.dumps({"dependencies": {"net8.0": {"Serilog": {"resolved": "4.0.1"}}}}),
        encoding="utf-8",
    )
    inventory = DependencyResolver(root).inventory()
    assert inventory.find("serde")[0].resolved == "1.0.210"
    assert inventory.find("tokio")[0].declared == "1.40"
    assert inventory.find("criterion")[0].scope is DependencyScope.DEVELOPMENT
    assert inventory.find("github.com/gin-gonic/gin")[0].resolved == "v1.10.0"
    assert inventory.find("org.springframework:spring-core")[0].declared == "6.1.5"
    assert inventory.find("junit:junit")[0].scope is DependencyScope.DEVELOPMENT
    assert inventory.find("com.squareup.okhttp3:okhttp")[0].declared == "4.12.0"
    assert inventory.find("Serilog")[0].resolved == "4.0.1"
    assert set(inventory.ecosystems()) == {
        Ecosystem.RUST,
        Ecosystem.GO,
        Ecosystem.JVM,
        Ecosystem.DOTNET,
    }


def test_missing_lockfile_leaves_only_a_declared_constraint(tmp_path: Path) -> None:
    root = tmp_path / "nolock"
    root.mkdir()
    (root / "package.json").write_text(
        json.dumps({"dependencies": {"next": "^15.0.0"}}), encoding="utf-8"
    )
    record = DependencyResolver(root).inventory().find("next")[0]
    assert record.declared == "^15.0.0"
    assert record.resolved is None
    assert record.effective_version is None


def test_malformed_and_oversized_manifests_are_reported_not_raised(tmp_path: Path) -> None:
    root = tmp_path / "broken"
    root.mkdir()
    (root / "package.json").write_text("{not json", encoding="utf-8")
    (root / "Cargo.toml").write_text("[dependencies\n", encoding="utf-8")
    (root / "pom.xml").write_text(
        '<!DOCTYPE lolz [<!ENTITY a "boom">]><project/>', encoding="utf-8"
    )
    records, reports = ManifestScanner(root).scan()
    assert records == ()
    assert {item.path for item in reports} == {"package.json", "Cargo.toml", "pom.xml"}
    assert all(not item.parsed and item.detail for item in reports)


def test_xml_manifests_refuse_dtd_and_entity_declarations(tmp_path: Path) -> None:
    """The refusal happens in the parser, not by inspecting the text."""
    root = tmp_path / "xxe"
    root.mkdir()
    (root / "a.csproj").write_text(
        '<!DOCTYPE lolz [<!ENTITY a "boom">]><Project><ItemGroup>'
        '<PackageReference Include="X" Version="1" /></ItemGroup></Project>',
        encoding="utf-8",
    )
    (root / "b.csproj").write_text(
        '<!DOCTYPE foo SYSTEM "file:///etc/passwd"><Project/>', encoding="utf-8"
    )
    records, reports = ManifestScanner(root).scan()
    assert records == ()
    assert {item.path for item in reports} == {"a.csproj", "b.csproj"}
    assert all(not item.parsed and "malformed manifest" in item.detail for item in reports)


def test_xml_manifests_still_parse_namespaced_documents(tmp_path: Path) -> None:
    root = tmp_path / "ns"
    root.mkdir()
    (root / "pom.xml").write_text(
        '<project xmlns="http://maven.apache.org/POM/4.0.0"><dependencies>'
        "<dependency><groupId>org.example</groupId><artifactId>lib</artifactId>"
        "<version>1.2.3</version></dependency></dependencies></project>",
        encoding="utf-8",
    )
    assert DependencyResolver(root).inventory().find("org.example:lib")[0].declared == "1.2.3"


def test_scanner_skips_vendored_directories(tmp_path: Path) -> None:
    root = tmp_path / "skip"
    (root / "node_modules" / "dep").mkdir(parents=True)
    (root / "node_modules" / "dep" / "package.json").write_text(
        json.dumps({"dependencies": {"ghost": "1"}}), encoding="utf-8"
    )
    (root / "package.json").write_text(
        json.dumps({"dependencies": {"real": "1"}}), encoding="utf-8"
    )
    inventory = DependencyResolver(root).inventory()
    assert inventory.find("ghost") == ()
    assert inventory.find("real")


# -- documentation service --------------------------------------------------


def _service(
    tmp_path: Path, provider: DependencyDocumentationProvider | None = None, **overrides: Any
) -> DependencyIntelligence:
    root = tmp_path / "svc"
    _python_project(root)
    config = CortexConfig(
        project_root=root,
        dependency_docs=DependencyDocsConfig(enabled=True, **overrides),
    )
    return DependencyIntelligence(root, config, provider)


@pytest.mark.asyncio
async def test_documentation_combines_resolved_version_with_provider_result(
    tmp_path: Path,
) -> None:
    provider = FakeDocumentationProvider()
    service = _service(tmp_path, provider)
    result = await service.docs("httpx", "how do I stream a response")
    assert result.available
    assert result.dependency is not None and result.dependency.resolved == "0.27.2"
    assert ("resolve", "httpx", "0.27.2") in provider.calls
    assert result.evidence[0].content.endswith("middleware API")
    assert result.cache_state == "miss"
    assert result.report().state is ProviderState.AVAILABLE


@pytest.mark.asyncio
async def test_documentation_cache_hit_avoids_a_second_provider_call(tmp_path: Path) -> None:
    provider = FakeDocumentationProvider()
    service = _service(tmp_path, provider)
    await service.docs("httpx", "streaming")
    calls = len(provider.calls)
    cached = await service.docs("httpx", "  STREAMING ")
    assert cached.cache_state == "hit"
    assert len(provider.calls) == calls


@pytest.mark.asyncio
async def test_provider_failures_fall_back_to_local_facts(tmp_path: Path) -> None:
    for reason, retryable in (
        ("documentation provider timed out", True),
        ("documentation provider rate limit reached", True),
        ("documentation provider returned a malformed response", False),
    ):
        provider = FakeDocumentationProvider(
            failure=DocumentationUnavailable(reason, retryable=retryable)
        )
        service = _service(tmp_path, provider)
        result = await service.docs("httpx", "streaming")
        assert not result.available
        assert result.provider_state is ProviderState.OFFLINE
        assert result.detail == reason
        assert result.dependency is not None and result.dependency.resolved == "0.27.2"
        assert result.report().fallback


@pytest.mark.asyncio
async def test_stale_cache_is_served_offline_but_always_marked_stale(tmp_path: Path) -> None:
    provider = FakeDocumentationProvider()
    service = _service(tmp_path, provider, cache_ttl_seconds=1)
    await service.docs("httpx", "streaming")

    key = service.cache.key(provider.key, "httpx", "0.27.2", "streaming")
    entries = service.cache.state.read({})
    entries["entries"][key]["created"] = time.time() - 10_000
    service.cache.state.write(entries)

    service._provider = FakeDocumentationProvider(
        failure=DocumentationUnavailable("offline", retryable=True)
    )
    result = await service.docs("httpx", "streaming")
    assert result.cache_state == "stale"
    assert result.evidence[0].stale is True
    assert result.provider_state is ProviderState.OFFLINE


@pytest.mark.asyncio
async def test_documentation_is_disabled_and_credential_free_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "default"
    _python_project(root)
    service = DependencyIntelligence(root, CortexConfig(project_root=root))
    assert service.status().label == "disabled"
    result = await service.docs("httpx", "streaming")
    assert result.provider_state is ProviderState.NOT_CONFIGURED
    assert not result.available
    assert result.dependency is not None

    monkeypatch.delenv(API_KEY_ENV, raising=False)
    enabled = DependencyIntelligence(
        root,
        CortexConfig(project_root=root, dependency_docs=DependencyDocsConfig(enabled=True)),
    )
    assert enabled.status().label == "credentials missing"
    missing = await enabled.docs("httpx", "streaming")
    assert missing.provider_state is ProviderState.CREDENTIALS_MISSING
    assert API_KEY_ENV in missing.detail


@pytest.mark.asyncio
async def test_dependency_context_includes_manifest_provenance(tmp_path: Path) -> None:
    service = _service(tmp_path, FakeDocumentationProvider())
    payload = await service.context("httpx", "streaming")
    assert payload["resolved_version"] == "0.27.2"
    assert payload["declared_version"] == ">=0.27,<1"
    assert "uv.lock" in {item["path"] for item in payload["manifests"]}
    assert payload["ecosystems"] == ["python"]


# -- remote transport -------------------------------------------------------


def _remote_config(base_url: str, **overrides: Any) -> DependencyDocsConfig:
    options: dict[str, Any] = {"max_retries": 0, **overrides}
    return DependencyDocsConfig(enabled=True, base_url=base_url, **options)


@pytest.mark.asyncio
async def test_remote_provider_sends_only_library_version_and_query(tmp_path: Path) -> None:
    search = json.dumps({"results": [{"id": "/vercel/next.js", "title": "Next", "versions": ["15.4.3"]}]})
    with _StubServer(
        {
            "/api/v2/libs/search": (200, "application/json", search),
            "/api/v2/context": (200, "text/plain", "middleware(request) is the current API"),
        }
    ) as server:
        provider = RemoteDocumentationProvider(_remote_config(server.base_url), "ctx7sk-secret")
        resolution = await provider.resolve_library("next", "auth middleware", "15.4.3")
        assert resolution.library_id == "/vercel/next.js"
        assert resolution.matched_version == "15.4.3"
        evidence = await provider.query_docs(resolution.library_id, "auth middleware", "15.4.3")
        assert evidence[0].content.startswith("middleware(request)")

    payloads = " ".join(_StubHandler.bodies)
    assert "next" in payloads and "auth+middleware" in payloads
    assert "pyproject" not in payloads and "src" not in payloads
    assert any(
        headers.get("Authorization") == "Bearer ctx7sk-secret"
        for _, headers in _StubHandler.seen
    )


@pytest.mark.asyncio
async def test_remote_provider_maps_status_codes_to_explicit_reasons() -> None:
    cases = {
        429: "rate limit",
        401: "credentials",
        404: "not known",
        500: "status 500",
    }
    for status, expected in cases.items():
        with _StubServer({"/api/v2/libs/search": (status, "application/json", "{}")}) as server:
            provider = RemoteDocumentationProvider(_remote_config(server.base_url), "key")
            with pytest.raises(DocumentationUnavailable, match=expected):
                await provider.resolve_library("next", "q", None)


@pytest.mark.asyncio
async def test_remote_provider_rejects_malformed_empty_and_oversized_responses() -> None:
    with _StubServer({"/api/v2/libs/search": (200, "application/json", "not json")}) as server:
        provider = RemoteDocumentationProvider(_remote_config(server.base_url), "key")
        with pytest.raises(DocumentationUnavailable, match="malformed"):
            await provider.resolve_library("next", "q", None)

    with _StubServer(
        {"/api/v2/libs/search": (200, "application/json", json.dumps({"results": []}))}
    ) as server:
        provider = RemoteDocumentationProvider(_remote_config(server.base_url), "key")
        with pytest.raises(DocumentationUnavailable, match="no documented library"):
            await provider.resolve_library("next", "q", None)

    with _StubServer(
        {"/api/v2/libs/search": (200, "application/json", json.dumps({"error": "boom"}))}
    ) as server:
        provider = RemoteDocumentationProvider(_remote_config(server.base_url), "key")
        with pytest.raises(DocumentationUnavailable, match="boom"):
            await provider.resolve_library("next", "q", None)

    with _StubServer(
        {"/api/v2/context": (200, "text/plain", "x" * 5_000)}
    ) as server:
        provider = RemoteDocumentationProvider(
            _remote_config(server.base_url, max_response_bytes=64), "key"
        )
        with pytest.raises(DocumentationUnavailable, match="size limit"):
            await provider.query_docs("/lib", "q", None)


@pytest.mark.asyncio
async def test_remote_provider_reports_empty_documentation_and_unreachable_hosts() -> None:
    with _StubServer({"/api/v2/context": (200, "text/plain", "   ")}) as server:
        provider = RemoteDocumentationProvider(_remote_config(server.base_url), "key")
        with pytest.raises(DocumentationUnavailable, match="no documentation available"):
            await provider.query_docs("/lib", "q", "1.0")

    unreachable = RemoteDocumentationProvider(
        _remote_config("http://127.0.0.1:1/api"), "key"
    )
    with pytest.raises(DocumentationUnavailable, match="unreachable"):
        await unreachable.resolve_library("next", "q", None)

    with pytest.raises(DocumentationUnavailable, match="http"):
        await RemoteDocumentationProvider(
            _remote_config("ftp://example.invalid"), "key"
        ).resolve_library("next", "q", None)

    for base, expected in (
        ("https://user:secret@example.invalid/api", "credentials"),
        ("https:///api", "must name a host"),
    ):
        with pytest.raises(DocumentationUnavailable, match=expected):
            await RemoteDocumentationProvider(
                _remote_config(base), "key"
            ).resolve_library("next", "q", None)

    disabled = RemoteDocumentationProvider(DependencyDocsConfig(enabled=False), "key")
    with pytest.raises(DocumentationUnavailable, match="not enabled"):
        await disabled.resolve_library("next", "q", None)
    assert await disabled.health() is False


@pytest.mark.asyncio
async def test_remote_provider_retries_only_retryable_failures() -> None:
    attempts: list[float] = []

    class _Flaky(RemoteDocumentationProvider):
        def _fetch(self, url: str):  # type: ignore[override]
            attempts.append(time.monotonic())
            if len(attempts) < 2:
                raise DocumentationUnavailable("temporary", retryable=True)
            return super()._fetch(url)

    search = json.dumps({"results": [{"id": "/lib"}]})
    with _StubServer({"/api/v2/libs/search": (200, "application/json", search)}) as server:
        provider = _Flaky(_remote_config(server.base_url, max_retries=2), "key")
        resolution = await provider.resolve_library("lib", "q", None)
    assert resolution.library_id == "/lib"
    assert len(attempts) == 2


def test_secret_redaction_covers_keys_tokens_and_query_parameters() -> None:
    assert "ctx7sk" not in redact_secrets("failed for ctx7sk-abc123")
    assert "topsecret" not in redact_secrets("Bearer topsecret")
    assert "hunter2" not in redact_secrets("https://x/y?api_key=hunter2&z=1")


def test_api_key_comes_only_from_the_configured_environment_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "keys"
    _python_project(root)
    config = CortexConfig(
        project_root=root,
        dependency_docs=DependencyDocsConfig(enabled=True, api_key_env="CODECORTEX_TEST_KEY"),
    )
    service = DependencyIntelligence(root, config)
    monkeypatch.delenv("CODECORTEX_TEST_KEY", raising=False)
    assert service.api_key() is None
    monkeypatch.setenv("CODECORTEX_TEST_KEY", "  ctx7sk-value  ")
    assert service.api_key() == "ctx7sk-value"
    assert service.status().credentials_present


def test_documentation_cache_reports_writability_and_survives_corruption(tmp_path: Path) -> None:
    cache = DocumentationCache(tmp_path / "cache" / "docs.json", ttl_seconds=60)
    assert cache.writable()
    assert cache.get("missing").hit is False
    cache.put("k", [DocumentationEvidence(library_id="/l", content="body", provider="p")])
    lookup = cache.get("k")
    assert lookup.hit and lookup.evidence is not None and lookup.evidence[0].content == "body"
    cache.state.write({"version": 999})
    assert cache.get("k").hit is False


# -- evidence provider ------------------------------------------------------


@pytest.mark.asyncio
async def test_dependency_evidence_carries_version_provenance(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    _python_project(root)
    config = CortexConfig(
        project_root=root, dependency_docs=DependencyDocsConfig(enabled=True)
    )
    provider = DependencyEvidenceProvider(root, config, FakeDocumentationProvider())
    bundle = await provider.collect(
        EvidenceRequest(query="how do I stream", metadata={"library": "httpx"})
    )
    record = bundle.records[0]
    assert record.kind is EvidenceKind.DOCUMENTATION
    assert record.trust is TrustTier.STRUCTURAL
    assert record.metadata["resolved_version"] == "0.27.2"
    assert record.metadata["declared_version"] == ">=0.27,<1"
    assert await provider.health() is True

    empty = await provider.collect(EvidenceRequest(query="nothing named"))
    assert empty.records == []
    assert (empty.report_for("dependency_docs") or record).state is ProviderState.NOT_CONFIGURED


def test_evidence_provider_runs_without_an_event_loop_conflict(tmp_path: Path) -> None:
    root = tmp_path / "loop"
    _python_project(root)
    provider = DependencyEvidenceProvider(root, CortexConfig(project_root=root))
    assert asyncio.run(provider.health()) is False
