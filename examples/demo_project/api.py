from auth.service import AuthService
from auth.tokens import TokenStore


def refresh(user_id: str) -> str:
    return AuthService(TokenStore()).refresh_token(user_id)
