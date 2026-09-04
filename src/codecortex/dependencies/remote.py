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
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from codecortex.config import DependencyDocsConfig
from codecortex.dependencies.contracts import DependencyDocumentationProvider
from codecortex.dependencies.models import (
    DocumentationEvidence,
    DocumentationUnavailable,
    LibraryResolution,
)
from codecortex.dependencies.versions import pin_library_id, select_version

#: A library identifier: ``/owner/repo`` with an optional ``/version`` or
#: ``@version`` pin. Anything else - a URL, an absolute path, a traversal - is
#: refused, because this value arrives in a provider-controlled response body.
_LIBRARY_ID = re.compile(r"/[A-Za-z0-9._\-]+(?:/[A-Za-z0-9._\-]+)*(?:@[A-Za-z0-9._\-]+)?")


def _optional_str(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_float(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        str(item).strip()
        for item in value
        if isinstance(item, (str, int, float)) and not isinstance(item, bool)
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

#: Provider-authored text is quoted back in diagnostics, so it is bounded.
_MAX_PROVIDER_MESSAGE = 400

#: Documentation states the provider publishes. Only a finalized library has
#: documentation that is complete enough to present as evidence.
FINALIZED_STATE = "finalized"
PENDING_STATES = frozenset({"initial"})
UNUSABLE_STATES = frozenset({"error", "delete"})


def redact_secrets(text: str) -> str:
    """Remove anything that looks like a credential from diagnostic text."""
    return _SECRET_PATTERN.sub("[redacted]", text)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface a redirect instead of following it.

    The provider uses ``301`` to say "this library moved to another library
    id", with the target in the response body. Following it as an HTTP
    redirect would either fail (there is no ``Location``) or fetch a URL the
    caller never validated.
    """

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


class _LibraryRedirect(DocumentationUnavailable):
    """The provider redirected this library to a different identifier."""

    def __init__(self, payload: dict[str, object]) -> None:
        target = payload.get("redirectUrl") or payload.get("libraryId") or ""
        message = payload.get("message")
        super().__init__(
            "documentation provider redirected this library"
            + (f": {redact_secrets(str(message))[:_MAX_PROVIDER_MESSAGE]}" if message else "")
        )
        self.target = str(target).strip()


#: Statuses the provider documents. Each is handled explicitly, because the
#: difference between them is the difference between "no documentation" and
#: "documentation that is not ready yet" and "you are being rate limited".
#:
#: Source: the pinned upstream OpenAPI contract for GET /v2/libs/search and
#: GET /v2/context, and the published error-handling table.
HTTP_ACCEPTED = 202
HTTP_MOVED_PERMANENTLY = 301

#: Longest a Retry-After hint is honoured. A provider asking for an hour must
#: not turn one MCP call into an hour-long block; the request fails and the
#: hint is reported instead.
MAX_RETRY_AFTER_SECONDS = 30.0

#: How many library redirections are followed before giving up.
MAX_REDIRECTS = 2


@dataclass(frozen=True, slots=True)
class _Response:
    status: int
    body: bytes
    content_type: str
    retry_after: float | None = None


def parse_retry_after(value: str | None, *, now: float | None = None) -> float | None:
    """Parse a ``Retry-After`` header, which may be seconds or an HTTP date.

    Returns None when the header is absent or unparseable, so a malformed hint
    falls back to the caller's own bounded backoff rather than being trusted.
    """
    if not value:
        return None
    text = value.strip()
    try:
        seconds = float(text)
    except ValueError:
        try:
            # Raises on anything that is not an HTTP-date, including None-ish
            # and truncated values; a bad hint must not escape as an exception.
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if parsed is None:  # pragma: no cover - defensive, older behaviour
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        reference = now if now is not None else datetime.now(UTC).timestamp()
        seconds = parsed.timestamp() - reference
    return max(0.0, seconds)


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
            # The scheme is restricted to http/https by _url() above. Redirects
            # are not followed automatically: the provider uses 301 to signal a
            # *library* redirection with a JSON body, which is handled by the
            # caller after validating the new identifier.
            opener = urllib.request.build_opener(_NoRedirect)
            with opener.open(request, timeout=timeout) as response:  # nosec B310
                body = response.read(self.config.max_response_bytes + 1)
                if len(body) > self.config.max_response_bytes:
                    raise DocumentationUnavailable(
                        "documentation response exceeded the configured size limit"
                    )
                return _Response(
                    status=int(response.status),
                    body=body,
                    content_type=str(response.headers.get("Content-Type", "")),
                    retry_after=parse_retry_after(response.headers.get("Retry-After")),
                )
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from None
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

    def _http_error(self, exc: urllib.error.HTTPError) -> DocumentationUnavailable:
        """Translate a documented status into a typed, honest failure.

        Every status the provider documents is handled by name. The default
        arm exists for a status the contract does not list; it is retried only
        when it is a server error, because retrying a client error just repeats
        it.
        """
        code = exc.code
        retry_after = parse_retry_after(exc.headers.get("Retry-After") if exc.headers else None)

        if code == HTTP_MOVED_PERMANENTLY:
            # A library redirection carries its target in the body, not in a
            # Location header, so it is surfaced for the caller to validate.
            return _LibraryRedirect(self._error_body(exc))
        if code == 400:
            return DocumentationUnavailable(
                f"documentation provider rejected the request: {self._error_message(exc)}"
            )
        if code == 401:
            return DocumentationUnavailable(
                "documentation provider rejected the configured credentials"
            )
        if code == 402:
            return DocumentationUnavailable(
                "documentation provider spending limit reached for this account"
            )
        if code == 403:
            return DocumentationUnavailable(
                "documentation provider denied access to this library"
            )
        if code == 404:
            return DocumentationUnavailable("library not known to the documentation provider")
        if code == 409:
            return DocumentationUnavailable(
                f"documentation provider reported a conflict: {self._error_message(exc)}"
            )
        if code == 422:
            return DocumentationUnavailable(
                f"documentation provider cannot process this library: {self._error_message(exc)}"
            )
        if code == 429:
            return DocumentationUnavailable(
                "documentation provider rate limit reached",
                retryable=True,
                retry_after=retry_after,
            )
        if code in {500, 502, 503, 504}:
            return DocumentationUnavailable(
                f"documentation provider returned status {code}",
                retryable=True,
                retry_after=retry_after,
            )
        return DocumentationUnavailable(
            f"documentation provider returned status {code}",
            retryable=code >= 500,
            retry_after=retry_after,
        )

    def _error_body(self, exc: urllib.error.HTTPError) -> dict[str, object]:
        """Read a bounded error body, tolerating a body that is not JSON."""
        try:
            raw = exc.read(self.config.max_response_bytes + 1)
        except OSError:  # pragma: no cover - the body was already consumed
            return {}
        if len(raw) > self.config.max_response_bytes:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _error_message(self, exc: urllib.error.HTTPError) -> str:
        """Return the provider's own message, redacted, or a neutral fallback."""
        payload = self._error_body(exc)
        message = payload.get("message") or payload.get("error")
        if isinstance(message, str) and message.strip():
            return redact_secrets(message.strip())[:_MAX_PROVIDER_MESSAGE]
        return f"status {exc.code}"

    async def _get(self, path: str, params: dict[str, str]) -> _Response:
        """Fetch one endpoint with bounded retries, honouring ``Retry-After``.

        A provider-supplied wait is respected up to
        :data:`MAX_RETRY_AFTER_SECONDS`; a longer hint fails the request and is
        reported, rather than turning one query into an unbounded sleep.
        """
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
                delay = RETRY_BACKOFF_SECONDS * (attempt + 1)
                if exc.retry_after is not None:
                    if exc.retry_after > MAX_RETRY_AFTER_SECONDS:
                        raise DocumentationUnavailable(
                            f"{exc.reason}; provider asked for a "
                            f"{exc.retry_after:.0f}s wait, which exceeds the "
                            f"{MAX_RETRY_AFTER_SECONDS:.0f}s bound",
                            retryable=True,
                            retry_after=exc.retry_after,
                        ) from None
                    delay = max(delay, exc.retry_after)
                await asyncio.sleep(delay)
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
            raise DocumentationUnavailable(
                redact_secrets(error)[:_MAX_PROVIDER_MESSAGE]
            )
        results = payload.get("results")
        if not isinstance(results, list) or not results:
            raise DocumentationUnavailable(f"no documented library matched {name!r}")

        best = self._first_usable_result(results, name)
        library_id = str(best.get("id", "")).strip()
        versions = _string_tuple(best.get("versions"))
        selection = select_version(version, versions)
        return LibraryResolution(
            library_id=library_id,
            title=_optional_str(best.get("title")),
            description=_optional_str(best.get("description")),
            versions=versions,
            matched_version=selection.provider_version,
            provider=self.key,
            score=_optional_float(best.get("trustScore")),
            state=_optional_str(best.get("state")),
            version_match=selection.match.value,
            version_detail=selection.detail,
        )

    def _first_usable_result(
        self, results: list[object], name: str
    ) -> dict[str, object]:
        """Pick the first result that is shaped like a library and is usable.

        The provider publishes a document state per library. A library it is
        still ingesting, or one it failed on, has no complete documentation, so
        it is skipped rather than queried and presented as an answer.
        """
        pending: str | None = None
        for item in results:
            if not isinstance(item, dict):
                continue
            filtered = {
                key: value for key, value in item.items() if key in _ALLOWED_RESULT_KEYS
            }
            if not str(filtered.get("id", "")).strip():
                continue
            state = _optional_str(filtered.get("state")).lower()
            if state in UNUSABLE_STATES:
                continue
            if state in PENDING_STATES:
                pending = pending or str(filtered.get("id"))
                continue
            return filtered
        if pending is not None:
            raise DocumentationUnavailable(
                f"documentation for {pending} is still being prepared by the provider",
                pending=True,
            )
        raise DocumentationUnavailable(
            f"no usable documented library matched {name!r}"
        )

    async def query_docs(
        self,
        library_id: str,
        query: str,
        version: str | None,
    ) -> list[DocumentationEvidence]:
        """Fetch documentation, following at most a bounded chain of redirects."""
        target = pin_library_id(library_id, version)
        seen = {target}
        for _ in range(MAX_REDIRECTS + 1):
            try:
                response = await self._get(
                    "v2/context", {"query": query, "libraryId": target}
                )
            except _LibraryRedirect as redirect:
                target = self._redirect_target(redirect, seen)
                seen.add(target)
                continue
            return self._documentation(response, library_id, target, query, version)
        raise DocumentationUnavailable(
            f"documentation provider redirected {library_id} more than "
            f"{MAX_REDIRECTS} times"
        )

    @staticmethod
    def _redirect_target(redirect: _LibraryRedirect, seen: set[str]) -> str:
        """Validate a redirection target before it is used as a library id.

        The target arrives in a provider-controlled response body, so it is
        checked rather than trusted: it must be a bare library path, not a URL,
        not an absolute filesystem path, and not one already visited.
        """
        target = redirect.target
        if not target:
            raise DocumentationUnavailable(
                "documentation provider signalled a redirect without a target"
            ) from None
        if not _LIBRARY_ID.fullmatch(target):
            raise DocumentationUnavailable(
                f"documentation provider redirected to an invalid library id: "
                f"{redact_secrets(target)[:_MAX_PROVIDER_MESSAGE]!r}"
            ) from None
        if target in seen:
            raise DocumentationUnavailable(
                f"documentation provider redirect loops back to {target}"
            ) from None
        return target

    def _documentation(
        self,
        response: _Response,
        library_id: str,
        target: str,
        query: str,
        version: str | None,
    ) -> list[DocumentationEvidence]:
        """Turn one successful response into evidence, or an honest failure.

        A ``202`` means the provider accepted the library but has not finished
        preparing its documentation. Its body is an explanatory error object,
        not documentation, so returning it would fabricate an answer.
        """
        if response.status == HTTP_ACCEPTED:
            raise DocumentationUnavailable(
                f"documentation for {library_id} is not finalized yet",
                pending=True,
                retry_after=response.retry_after,
            )
        text = response.body.decode("utf-8", errors="replace").strip()
        if response.content_type.startswith("application/json"):
            payload = self._json(response)
            error = payload.get("error")
            if isinstance(error, str) and error:
                raise DocumentationUnavailable(
                    redact_secrets(error)[:_MAX_PROVIDER_MESSAGE]
                )
            data = payload.get("data")
            text = data.strip() if isinstance(data, str) else ""
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
                metadata={"query": query, "requested_library_id": target},
            )
        ]
