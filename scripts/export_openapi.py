#!/usr/bin/env python3
"""Export the current CodeCortex HTTP schema without starting a server."""
from __future__ import annotations

import json
from pathlib import Path

from codecortex.api.app import create_app


def main() -> None:
    output = Path("docs/platform/openapi.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    app = create_app(state_dir=Path(".codecortex/openapi-export"))
    output.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
