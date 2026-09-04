#!/usr/bin/env python3
"""Re-download the pinned upstream conformance fixtures and verify their digests.

The fixtures under ``tests/fixtures/upstream`` are committed so that conformance
tests run offline and deterministically. This script is the documented way to
refresh them when a pin is deliberately moved: it fetches every file named in a
``PROVENANCE.json`` manifest and compares the SHA-256 against the manifest.

By default it only verifies; pass ``--write`` to update the working tree, which
is the intended flow when the manifest itself has been repointed at a new
commit.

Exit codes: ``0`` everything matches (or was written), ``1`` a digest mismatch
or download failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "upstream"
TIMEOUT_SECONDS = 30


def _fetch(url: str) -> bytes:
    if not url.startswith("https://"):
        raise ValueError(f"refusing to fetch a non-HTTPS url: {url}")
    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        payload: bytes = response.read()
    return payload


def _check_manifest(manifest_path: Path, *, write: bool) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for entry in manifest["files"]:
        local = REPO_ROOT / entry["local_path"]
        expected = entry["sha256"]
        try:
            payload = _fetch(entry["upstream_url"])
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            problems.append(f"{entry['local_path']}: download failed: {exc}")
            continue
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            problems.append(
                f"{entry['local_path']}: upstream digest {actual} does not match "
                f"manifest digest {expected}"
            )
            continue
        if write:
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(payload)
        elif not local.exists():
            problems.append(f"{entry['local_path']}: missing from the working tree")
        elif hashlib.sha256(local.read_bytes()).hexdigest() != expected:
            problems.append(f"{entry['local_path']}: working tree copy has drifted")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="overwrite the working-tree copies with the verified upstream bytes",
    )
    args = parser.parse_args()

    manifests = sorted(FIXTURE_ROOT.glob("*/PROVENANCE.json"))
    if not manifests:
        print("no upstream fixture manifests found", file=sys.stderr)
        return 1

    problems: list[str] = []
    for manifest_path in manifests:
        problems.extend(_check_manifest(manifest_path, write=args.write))

    if problems:
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        return 1
    print(f"verified {len(manifests)} upstream fixture manifest(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
