"""Credential-gated smoke test against the real documentation service.

This never runs in normal CI. It runs only when ``CODECORTEX_DEPENDENCY_DOCS_API_KEY``
is set, and it is reported as SKIPPED - never as passed - when it is not. A
skipped test here means the live path was not exercised; it does not mean the
live path works.

The test also re-asserts the privacy boundary against the real endpoint: only
a library name, a version, and the user's question may leave the machine.
"""

from __future__ import annotations

import os

import pytest

from codecortex.config import DependencyDocsConfig
from codecortex.dependencies.models import DocumentationUnavailable
from codecortex.dependencies.remote import RemoteDocumentationProvider

API_KEY_ENV = "CODECORTEX_DEPENDENCY_DOCS_API_KEY"
BASE_URL_ENV = "CODECORTEX_DEPENDENCY_DOCS_BASE_URL"

pytestmark = pytest.mark.skipif(
    not os.environ.get(API_KEY_ENV, "").strip()
    or not os.environ.get(BASE_URL_ENV, "").strip(),
    reason=(
        "SKIPPED - live documentation provider requires both "
        f"{API_KEY_ENV} and {BASE_URL_ENV}"
    ),
)


def _provider() -> RemoteDocumentationProvider:
    return RemoteDocumentationProvider(
        DependencyDocsConfig(
            enabled=True,
            base_url=os.environ[BASE_URL_ENV].strip(),
            max_retries=1,
        ),
        os.environ[API_KEY_ENV].strip(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("library", ["react", "next.js", "fastapi"])
async def test_a_common_library_resolves_and_returns_documentation(library: str) -> None:
    provider = _provider()
    resolution = await provider.resolve_library(library, "getting started", None)

    assert resolution.library_id.startswith("/")
    assert resolution.provider == provider.key

    evidence = await provider.query_docs(
        resolution.library_id, "getting started", resolution.matched_version
    )
    assert evidence
    assert evidence[0].content.strip()
    assert evidence[0].library_id == resolution.library_id


@pytest.mark.asyncio
async def test_an_unknown_library_fails_cleanly_rather_than_inventing_docs() -> None:
    provider = _provider()
    unknown = "codecortex-library-that-does-not-exist-9f3a2b"
    with pytest.raises(DocumentationUnavailable):
        resolution = await provider.resolve_library(unknown, "anything", None)
        await provider.query_docs(resolution.library_id, "anything", None)


@pytest.mark.asyncio
async def test_the_live_credential_never_appears_in_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A real key must not reach stdout, stderr, or an exception message."""
    key = os.environ[API_KEY_ENV].strip()
    provider = _provider()
    try:
        resolution = await provider.resolve_library("react", "hooks", None)
        await provider.query_docs(resolution.library_id, "hooks", resolution.matched_version)
    except DocumentationUnavailable as exc:
        assert key not in str(exc)
        assert key not in exc.reason
    captured = capsys.readouterr()
    assert key not in captured.out
    assert key not in captured.err
