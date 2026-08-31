# Packaging

The public brand and CLI remain **CodeCortex** and `cortex`.

The Python distribution is published as **`codecortex-ai`** to avoid colliding with unrelated packages already using the `codecortex` distribution name.

Install from PyPI after the first release:

```bash
uv tool install codecortex-ai
# or
pipx install codecortex-ai
```

The import package remains `codecortex` and the executables remain `cortex` and `codecortex`.
