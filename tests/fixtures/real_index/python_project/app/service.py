"""Cross-file references to both identically named functions."""

from app.auth import session_token as auth_token
from app.billing import session_token as billing_token


def build(user: str, plan: str) -> str:
    total = f"日本語 {auth_token(user)}"
    return total + "|" + billing_token(plan)
