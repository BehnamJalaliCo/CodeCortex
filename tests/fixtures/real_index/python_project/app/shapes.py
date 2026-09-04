"""Nested definitions and repeated local identifiers."""


def outer(value: str) -> str:
    total = value.upper()

    def inner(other: str) -> str:
        total = other.lower()
        return total

    return total + inner(value)
