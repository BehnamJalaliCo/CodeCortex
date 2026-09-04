"""Hosted MCP-compatible JSON transport with authentication, TLS, quotas and policy."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import json
import ssl
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ToolDispatcher = Callable[..., dict[str, Any] | Awaitable[dict[str, Any]]]
PolicyAuthorizer = Callable[[str, str], bool]


@dataclass(frozen=True, slots=True)
class RemoteMCPSettings:
    host: str = "127.0.0.1"
    port: int = 8765
    tls_cert: str | None = None
    tls_key: str | None = None
    max_requests_per_minute: int = 120
    max_body_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        if not 0 <= self.port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        if self.max_requests_per_minute < 1 or self.max_body_bytes < 1:
            raise ValueError("quota and body limit must be positive")
        if bool(self.tls_cert) != bool(self.tls_key):
            raise ValueError("tls_cert and tls_key must be configured together")


class BearerTokenAuthenticator:
    """Authenticate bearer tokens in constant time without storing plaintext tokens."""

    def __init__(self, tokens: dict[str, str]) -> None:
        if not tokens:
            raise ValueError("at least one principal token is required")
        self._digests = {
            hashlib.sha256(token.encode()).digest(): principal
            for principal, token in tokens.items()
            if principal.strip() and token
        }
        if not self._digests:
            raise ValueError("at least one valid principal token is required")

    def authenticate(self, authorization: str | None) -> str | None:
        if not authorization or not authorization.startswith("Bearer "):
            return None
        candidate = hashlib.sha256(authorization[7:].encode()).digest()
        for digest, principal in self._digests.items():
            if hmac.compare_digest(candidate, digest):
                return principal
        return None


@dataclass(frozen=True, slots=True)
class RemoteAccessPolicy:
    allowed_tools: dict[str, frozenset[str]] = field(default_factory=dict)
    denied_tools: frozenset[str] = frozenset()
    mutating_tools: frozenset[str] = frozenset()
    mutation_principals: frozenset[str] = frozenset()
    authorizer: PolicyAuthorizer | None = None
    default_allow: bool = False

    def allows(self, principal: str, tool: str) -> bool:
        if tool in self.denied_tools:
            return False
        if tool in self.mutating_tools and principal not in self.mutation_principals:
            return False
        allowed = self.allowed_tools.get(principal)
        static_allowed = (
            self.default_allow if allowed is None else "*" in allowed or tool in allowed
        )
        if not static_allowed:
            return False
        if self.authorizer is None:
            return True
        try:
            return bool(self.authorizer(principal, tool))
        except Exception:
            return False


class _SlidingWindowQuota:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def acquire(self, principal: str) -> bool:
        now = time.monotonic()
        threshold = now - self.window_seconds
        with self._lock:
            events = self._events[principal]
            while events and events[0] <= threshold:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


class RemoteMCPServer:
    def __init__(
        self,
        dispatcher: ToolDispatcher,
        authenticator: BearerTokenAuthenticator,
        policy: RemoteAccessPolicy,
        settings: RemoteMCPSettings | None = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.authenticator = authenticator
        self.policy = policy
        self.settings = settings or RemoteMCPSettings()
        self._quota = _SlidingWindowQuota(self.settings.max_requests_per_minute)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int] | None:
        if self._server is None:
            return None
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def _dispatch(self, tool: str, arguments: dict[str, Any], principal: str) -> Any:
        parameters: Mapping[str, inspect.Parameter]
        try:
            parameters = inspect.signature(self.dispatcher).parameters
        except (TypeError, ValueError):
            parameters = {}
        if len(parameters) >= 3:
            result = self.dispatcher(tool, arguments, principal)
        else:
            result = self.dispatcher(tool, arguments)
        if isinstance(result, Coroutine):
            return asyncio.run(result)
        return result

    def handle_call(
        self,
        authorization: str | None,
        payload: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        principal = self.authenticator.authenticate(authorization)
        if principal is None:
            return 401, {"error": "unauthorized"}
        tool = payload.get("tool")
        arguments = payload.get("arguments", {})
        if not isinstance(tool, str) or not tool.strip():
            return 400, {"error": "tool_required"}
        if not isinstance(arguments, dict):
            return 400, {"error": "arguments_must_be_object"}
        if not self.policy.allows(principal, tool):
            return 403, {"error": "forbidden"}
        if not self._quota.acquire(principal):
            return 429, {"error": "quota_exceeded"}
        try:
            result = self._dispatch(tool, arguments, principal)
            if not isinstance(result, dict):
                result = {"result": result}
            return 200, {"result": result, "principal": principal}
        except Exception:  # pragma: no cover - integration boundary
            return 500, {"error": "tool_failure", "error_id": uuid.uuid4().hex}

    def start(self, *, background: bool = True) -> tuple[str, int]:
        if self._server is not None:
            raise RuntimeError("remote MCP server is already running")
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "CodeCortexRemoteMCP/1"

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._write(200, {"status": "ok"})
                    return
                self._write(404, {"error": "not_found"})

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/mcp":
                    self._write(404, {"error": "not_found"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._write(400, {"error": "invalid_content_length"})
                    return
                if length < 1 or length > owner.settings.max_body_bytes:
                    self._write(413, {"error": "invalid_body_size"})
                    return
                try:
                    payload = json.loads(self.rfile.read(length))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._write(400, {"error": "invalid_json"})
                    return
                if not isinstance(payload, dict):
                    self._write(400, {"error": "body_must_be_object"})
                    return
                status, response = owner.handle_call(
                    self.headers.get("Authorization"), payload
                )
                self._write(status, response)

            def _write(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, sort_keys=True).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                del format, args

        server = ThreadingHTTPServer((self.settings.host, self.settings.port), Handler)
        if self.settings.tls_cert and self.settings.tls_key:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(self.settings.tls_cert, self.settings.tls_key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
        self._server = server
        if background:
            self._thread = threading.Thread(target=server.serve_forever, daemon=True)
            self._thread.start()
        else:  # pragma: no cover - command-line service mode
            server.serve_forever()
        address = self.address
        assert address is not None
        return address

    def close(self) -> None:
        server = self._server
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._server = None
        self._thread = None

    def __enter__(self) -> RemoteMCPServer:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        self.close()


class RemoteMCPClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_seconds: float = 30.0,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        normalized = base_url.rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must use http or https and include a hostname")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("base_url must not contain embedded credentials")
        self.base_url = normalized
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.ssl_context = ssl_context

    def call(
        self,
        tool: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps({"tool": tool, "arguments": arguments or {}}).encode()
        request = Request(
            f"{self.base_url}/mcp",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(  # nosec B310
                request,
                timeout=self.timeout_seconds,
                context=self.ssl_context,
            ) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read())
            except json.JSONDecodeError:
                detail = {"error": "http_error"}
            raise RuntimeError(
                f"remote MCP request failed ({exc.code}): {detail}"
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError("remote MCP response must be an object")
        result = payload.get("result", {})
        return result if isinstance(result, dict) else {"result": result}
