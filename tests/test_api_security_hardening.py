from codecortex.api.hardening import ApiHardeningSettings, SlidingWindowLimiter


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
