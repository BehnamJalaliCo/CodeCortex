"""Security middleware for the hosted web API."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ApiHardeningSettings:
    max_body_bytes: int = 2 * 1024 * 1024
    requests_per_minute: int = 600

    @classmethod
    def from_env(cls) -> ApiHardeningSettings:
        return cls(
            max_body_bytes=max(
                1024, int(os.getenv("CODECORTEX_API_MAX_BODY_BYTES", str(2 * 1024 * 1024)))
            ),
            requests_per_minute=max(1, int(os.getenv("CODECORTEX_API_REQUESTS_PER_MINUTE", "600"))),
        )


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = max(1, limit)
        self.window_seconds = window_seconds
        self._entries: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            bucket = self._entries[key]
            threshold = timestamp - self.window_seconds
            while bucket and bucket[0] <= threshold:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(timestamp)
            return True


def install_api_hardening(app: Any, settings: ApiHardeningSettings | None = None) -> None:
    from fastapi import Request
    from fastapi.responses import JSONResponse

    config = settings or ApiHardeningSettings.from_env()
    limiter = SlidingWindowLimiter(config.requests_per_minute)

    @app.middleware("http")
    async def harden(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > config.max_body_bytes:
                    return JSONResponse({"detail": "request body too large"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "invalid content-length"}, status_code=400)

        client = request.client.host if request.client else "unknown"
        if not limiter.allow(client):
            return JSONResponse(
                {"detail": "rate limit exceeded"}, status_code=429, headers={"Retry-After": "60"}
            )

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            host = request.headers.get("host")
            if origin and host and not (origin == f"http://{host}" or origin == f"https://{host}"):
                return JSONResponse({"detail": "cross-origin mutation rejected"}, status_code=403)

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response
