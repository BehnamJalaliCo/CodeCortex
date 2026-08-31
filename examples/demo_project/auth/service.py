from __future__ import annotations

from .tokens import TokenStore


class AuthService:
    def __init__(self, tokens: TokenStore) -> None:
        self.tokens = tokens

    def refresh_token(self, user_id: str) -> str:
        current = self.tokens.get(user_id)
        return self.tokens.rotate(user_id, current)
