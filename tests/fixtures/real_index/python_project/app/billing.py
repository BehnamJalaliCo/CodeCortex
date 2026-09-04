"""Billing service.

Declares its own session_token, unrelated to the authentication one.
"""


def session_token(plan: str) -> str:
    total = f"سلام {plan}"
    return "billing:" + total


def open_period(plan: str) -> str:
    return session_token(plan) + ":open"
