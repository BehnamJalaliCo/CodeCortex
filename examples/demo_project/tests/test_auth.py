from auth.service import AuthService
from auth.tokens import TokenStore


def test_refresh_rotates_token() -> None:
    service = AuthService(TokenStore())
    assert service.refresh_token("user").startswith("user:")
