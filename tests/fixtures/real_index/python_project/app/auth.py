"""Authentication service.

Declares session_token, which is a different symbol from the identically
named function in app.billing. Name alone cannot tell them apart.
"""


def session_token(user: str) -> str:
    # The emoji sits on the same line as the reference, so the column of
    # `user` differs between UTF-8 bytes, UTF-16 code units, and code points.
    total = f"🚀 {user}"
    return "auth:" + total


def revoke(user: str) -> str:
    return session_token(user) + ":revoked"
