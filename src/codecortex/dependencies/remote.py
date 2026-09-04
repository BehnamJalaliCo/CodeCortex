"""Opt-in remote documentation provider.

Privacy boundary
----------------
This provider sends exactly three things: the dependency name, the resolved
version, and the user's own question. It never sends source files, file paths,
Git history, memory contents, environment variables, or any other repository
content. Requests are only made when the capability is explicitly enabled in
configuration.

Availability
------------
The public upstream project behind this provider documents that parts of its
indexing and crawling backend are not part of its public repository, so this is
a hosted-service adapter, not a self-hostable stack. CodeCortex Core continues
to work with no network access at all; when this provider is unavailable the
dependency layer returns local manifest facts and an explicit
docs-unavailable state.
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from codecortex.config import DependencyDocsConfig
from codecortex.dependencies.contracts import DependencyDocumentationProvider
from codecortex.dependencies.models import (
    DocumentationEvidence,
    DocumentationUnavailable,
    LibraryResolution,
)

PROVIDER_KEY = "dependency_docs_remote"

#: Backoff between bounded retries, in seconds.
RETRY_BACKOFF_SECONDS = 0.5

#: Keys that may appear in a provider response; anything else is ignored.
_ALLOWED_RESULT_KEYS = frozenset(
    {
        "id",
        "title",
        "description",
        "versions",
        "branch",
        "totalTokens",
        "totalSnippets",
        "stars",
        "trustScore",
        "benchmarkScore",
        "state",
        "source",
        "lastUpdateDate",
    }
)

_SECRET_PATTERN = re.compile(r"(ctx7sk[A-Za-z0-9_\-]+|Bearer\s+\S+|api[_-]?key=[^\s&]+)", re.I)


def redact_secrets(text: str) -> str:
    """Remove anything that looks like a credential from diagnostic text."""
    return _SECRET_PATTERN.sub("[redacted]", text)


@dataclass(frozen=True, slots=True)
class _Response:
    status: int
    body: bytes
    content_type: str


class RemoteDocumentationProvider(DependencyDocumentationProvider):
    """Query a hosted, version-aware documentation service over HTTPS."""

    key = PROVIDER_KEY

    def __init__(
        self,
        config: DependencyDocsConfig,
        api_key: str | None = None,
        *,
        user_agent: str = "CodeCortex",
    ) -> None:
        self.config = config
        self._api_key = api_key
        self.user_agent = user_agent

    @property
    def configured(self) -> bool:
        return self.config.enabled

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key)

    # -- transport ----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json, text/plain", "User-Agent": self.user_agent}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _url(self, path: str, params: dict[str, str]) -> str:
        """Build a request URL from a validated base, rejecting anything else.

        The base URL comes from project configuration, so it is treated as
        untrusted: the scheme is restricted to http(s), a host must be present,
        and embedded credentials are refused. The URL is then rebuilt from those
        checked components rather than by concatenating the raw string.
        """
        parts = urllib.parse.urlsplit(self.config.base_url.rstrip("/"))
        if parts.scheme not in {"http", "https"}:
            raise DocumentationUnavailable(
                f"documentation provider base URL must be http(s): {self.config.base_url}"
            )
        if not parts.hostname:
            raise DocumentationUnavailable(
                "documentation provider base URL must name a host"
            )
        if parts.username or parts.password:
            raise DocumentationUnavailable(
                "documentation provider base URL must not embed credentials"
            )
        route = f"{parts.path}/{path.lstrip('/')}"
        return urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, route, urllib.parse.urlencode(params), "")
        )

    def _fetch(self, url: str) -> _Response:
        """Perform one bounded GET request.

        Raises:
            DocumentationUnavailable: on any transport or protocol failure.
        """
        request = urllib.request.Request(url, headers=self._headers(), method="GET")
        timeout = self.config.connect_timeout_seconds + self.config.read_timeout_seconds
        try:
            # The scheme is restricted to http/https by _url() above.
            with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
                body = response.read(self.config.max_response_bytes + 1)
                if len(body) > self.config.max_response_bytes:
                    raise DocumentationUnavailable(
                        "documentation response exceeded the configured size limit"
                    )
                return _Response(
                    status=int(response.status),
                    body=body,
                    content_type=str(response.headers.get("Content-Type", "")),
                )
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise DocumentationUnavailable(
                    "documentation provider rate limit reached", retryable=True
                ) from None
            if exc.code in {401, 403}:
                raise DocumentationUnavailable(
                    "documentation provider rejected the configured credentials"
                ) from None
            if exc.code == 404:
                raise DocumentationUnavailable("library not known to the documentation provider") from None
            raise DocumentationUnavailable(
                f"documentation provider returned status {exc.code}", retryable=exc.code >= 500
            ) from None
        except urllib.error.URLError as exc:
            raise DocumentationUnavailable(
                f"documentation provider unreachable: {redact_secrets(str(exc.reason))}",
                retryable=True,
            ) from None
        except TimeoutError:
            raise DocumentationUnavailable(
                "documentation provider timed out", retryable=True
            ) from None
        except OSError as exc:
            raise DocumentationUnavailable(
                f"documentation request failed: {redact_secrets(str(exc))}", retryable=True
            ) from None

    async def _get(self, path: str, params: dict[str, str]) -> _Response:
        if not self.configured:
            raise DocumentationUnavailable("dependency documentation is not enabled")
        url = self._url(path, params)
        attempts = self.config.max_retries + 1
        last: DocumentationUnavailable | None = None
        for attempt in range(attempts):
            try:
                return await asyncio.to_thread(self._fetch, url)
            except DocumentationUnavailable as exc:
                last = exc
                if not exc.retryable or attempt == attempts - 1:
                    raise
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
        raise last or DocumentationUnavailable("documentation request failed")

    @staticmethod
    def _json(response: _Response) -> dict[str, object]:
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise DocumentationUnavailable(
                "documentation provider returned a malformed response"
            ) from None
        if not isinstance(payload, dict):
            raise DocumentationUnavailable(
                "documentation provider returned an unexpected response shape"
            )
        return payload

    # -- provider contract --------------------------------------------------

    async def health(self) -> bool:
        return self.configured and self.has_credentials

    async def resolve_library(
        self,
        name: str,
        query: str,
        version: str | None,
    ) -> LibraryResolution:
        response = await self._get(
            "v2/libs/search", {"query": query or name, "libraryName": name}
        )
        payload = self._json(response)
        error = payload.get("error")
        if isinstance(error, str) and error:
            raise DocumentationUnavailable(redact_secrets(error))
        results = payload.get("results")
        if not isinstance(results, list) or not results:
            raise DocumentationUnavailable(f"no documented library matched {name!r}")
        best = next((item for item in results if isinstance(item, dict)), None)
        if best is None:
            raise DocumentationUnavailable(
                "documentation provider returned an unexpected response shape"
            )
        filtered = {key: value for key, value in best.items() if key in _ALLOWED_RESULT_KEYS}
        library_id = str(filtered.get("id", "")).strip()
        if not library_id:
            raise DocumentationUnavailable(
                "documentation provider returned a library without an identifier"
            )
        raw_versions = filtered.get("versions")
        versions = tuple(
            str(item) for item in raw_versions if isinstance(item, (str, int, float))
        ) if isinstance(raw_versions, list) else ()
        return LibraryResolution(
            library_id=library_id,
            title=str(filtered.get("title", "")),
            description=str(filtered.get("description", "")),
            versions=versions,
            matched_version=version if version in versions else None,
            provider=self.key,
            score=float(filtered.get("trustScore") or 0.0),
        )

    async def query_docs(
        self,
        library_id: str,
        query: str,
        version: str | None,
    ) -> list[DocumentationEvidence]:
        target = f"{library_id}/{version}" if version else library_id
        response = await self._get("v2/context", {"query": query, "libraryId": target})
        text = response.body.decode("utf-8", errors="replace").strip()
        if not text:
            raise DocumentationUnavailable(
                f"no documentation available for {library_id} at the requested version"
            )
        if response.content_type.startswith("application/json"):
            payload = self._json(response)
            data = payload.get("data")
            text = str(data).strip() if isinstance(data, str) else ""
            if not text:
                raise DocumentationUnavailable(
                    f"no documentation available for {library_id} at the requested version"
                )
        return [
            DocumentationEvidence(
                library_id=library_id,
                content=redact_secrets(text),
                version=version,
                title=library_id,
                provider=self.key,
                metadata={"query": query},
            )
        ]
