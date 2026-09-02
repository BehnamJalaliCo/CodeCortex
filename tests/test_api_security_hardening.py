from fastapi import FastAPI
from fastapi.testclient import TestClient

from codecortex.api.hardening import (
    ApiHardeningSettings,
    SlidingWindowLimiter,
    install_api_hardening,
)


def test_rate_limiter_enforces_window() -> None:
    limiter = SlidingWindowLimiter(2, window_seconds=60)
    assert limiter.allow("client", now=0)
    assert limiter.allow("client", now=1)
    assert not limiter.allow("client", now=2)
    assert limiter.allow("client", now=61)


def test_hardening_settings_have_safe_defaults() -> None:
    settings = ApiHardeningSettings()
    assert settings.max_body_bytes >= 1024
    assert settings.requests_per_minute > 0


def test_hardening_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("CODECORTEX_API_MAX_BODY_BYTES", "4096")
    monkeypatch.setenv("CODECORTEX_API_REQUESTS_PER_MINUTE", "7")

    settings = ApiHardeningSettings.from_env()

    assert settings.max_body_bytes == 4096
    assert settings.requests_per_minute == 7


def _hardened_client(*, max_body_bytes: int = 1024, requests_per_minute: int = 10) -> TestClient:
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/mutate")
    async def mutate() -> dict[str, str]:
        return {"status": "updated"}

    install_api_hardening(
        app,
        ApiHardeningSettings(
            max_body_bytes=max_body_bytes,
            requests_per_minute=requests_per_minute,
        ),
    )
    return TestClient(app)


def test_hardening_adds_security_headers() -> None:
    client = _hardened_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"


def test_hardening_rejects_invalid_and_oversized_content_length() -> None:
    client = _hardened_client(max_body_bytes=1024)

    invalid = client.post("/mutate", headers={"content-length": "invalid"})
    oversized = client.post("/mutate", headers={"content-length": "2048"})

    assert invalid.status_code == 400
    assert invalid.json() == {"detail": "invalid content-length"}
    assert oversized.status_code == 413
    assert oversized.json() == {"detail": "request body too large"}


def test_hardening_rejects_cross_origin_mutation() -> None:
    client = _hardened_client()

    response = client.post(
        "/mutate",
        headers={"host": "testserver", "origin": "https://example.com"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "cross-origin mutation rejected"}


def test_hardening_allows_same_origin_mutation() -> None:
    client = _hardened_client()

    response = client.post(
        "/mutate",
        headers={"host": "testserver", "origin": "http://testserver"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "updated"}


def test_hardening_rate_limit_returns_retry_after() -> None:
    client = _hardened_client(requests_per_minute=1)

    first = client.get("/health")
    second = client.get("/health")

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json() == {"detail": "rate limit exceeded"}
    assert second.headers["retry-after"] == "60"
