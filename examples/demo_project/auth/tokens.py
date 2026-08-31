from __future__ import annotations


class TokenStore:
    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}

    def get(self, user_id: str) -> str:
        return self._tokens.get(user_id, "initial")

    def rotate(self, user_id: str, previous: str) -> str:
        token = f"{user_id}:{len(previous) + 1}"
        self._tokens[user_id] = token
        return token
