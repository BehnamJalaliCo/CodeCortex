"""Small dependency-free Python client for the stable CodeCortex API."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]


class CodeCortexHttpError(RuntimeError):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__(f"CodeCortex API {status}: {detail}")


@dataclass(slots=True)
class CodeCortexClient:
    base_url: str = "http://127.0.0.1:7340"
    token: str | None = None
    timeout: float = 30.0
    transport: Transport | None = None
    api_version: str = "v1"

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url.rstrip('/')}/api/{self.api_version}/{path.lstrip('/')}"
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if self.transport is not None:
            status, body = self.transport(method, url, headers, data)
        else:
            request = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec B310 - URL is caller-configured SDK endpoint
                    status, body = response.status, response.read()
            except urllib.error.HTTPError as exc:
                status, body = exc.code, exc.read()
        decoded = json.loads(body.decode("utf-8")) if body else None
        if status >= 400:
            detail = decoded.get("detail", decoded) if isinstance(decoded, dict) else decoded
            raise CodeCortexHttpError(status, str(detail))
        return decoded

    def health(self) -> dict[str, Any]:
        payload: dict[str, Any] = self._request("GET", "health")
        return payload

    def repositories(self) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = self._request("GET", "repositories")
        return payload

    def repository_overview(self, repository_id: str) -> dict[str, Any]:
        payload: dict[str, Any] = self._request(
            "GET", f"repositories/{urllib.parse.quote(repository_id, safe='')}/overview"
        )
        return payload

    def search(self, repository_id: str, query: str, limit: int = 20) -> dict[str, Any]:
        payload: dict[str, Any] = self._request(
            "POST",
            f"repositories/{urllib.parse.quote(repository_id, safe='')}/search",
            {"query": query, "limit": limit},
        )
        return payload

    def context(self, repository_id: str, query: str, budget: int = 32000) -> dict[str, Any]:
        payload: dict[str, Any] = self._request(
            "POST",
            f"repositories/{urllib.parse.quote(repository_id, safe='')}/context",
            {"query": query, "budget": budget},
        )
        return payload

    def impact(self, repository_id: str, query: str) -> dict[str, Any]:
        payload: dict[str, Any] = self._request(
            "POST",
            f"repositories/{urllib.parse.quote(repository_id, safe='')}/impact",
            {"query": query},
        )
        return payload

    def pr_analysis(
        self, repository_id: str, base_ref: str, head_ref: str = "HEAD"
    ) -> dict[str, Any]:
        payload: dict[str, Any] = self._request(
            "POST",
            f"repositories/{urllib.parse.quote(repository_id, safe='')}/pr-analysis",
            {"base_ref": base_ref, "head_ref": head_ref},
        )
        return payload
