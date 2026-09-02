import json

from codecortex.sdk import CodeCortexClient, CodeCortexHttpError


def test_sdk_adds_auth_and_serializes_json() -> None:
    seen = {}

    def transport(method, url, headers, body):
        seen.update(method=method, url=url, headers=headers, body=body)
        return 200, json.dumps({"results": []}).encode()

    client = CodeCortexClient("https://example.test", token="secret", transport=transport)
    assert client.search("repo a", "find auth")["results"] == []
    assert seen["headers"]["Authorization"] == "Bearer secret"
    assert "repo%20a" in seen["url"]


def test_sdk_raises_typed_http_error() -> None:
    client = CodeCortexClient(transport=lambda *_: (403, b'{"detail":"denied"}'))
    try:
        client.health()
    except CodeCortexHttpError as exc:
        assert exc.status == 403
    else:
        raise AssertionError("expected CodeCortexHttpError")
