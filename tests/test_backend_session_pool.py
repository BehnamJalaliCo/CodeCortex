from pathlib import Path

from codecortex.backends.pool import BackendSessionPool


def test_pool_key_is_stable_for_environment_order():
    class Spec:
        key = "x"
        revision = "r"

    left = BackendSessionPool._key(Spec(), ("serve",), Path("."), {"B": "2", "A": "1"})
    right = BackendSessionPool._key(Spec(), ("serve",), Path("."), {"A": "1", "B": "2"})
    assert left == right
