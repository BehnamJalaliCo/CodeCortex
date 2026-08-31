# Contributing

CodeCortex is early, so small and focused changes are easier to review than large rewrites.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest -q
```

## Pull requests

Please keep a pull request focused on one problem. Add tests for behavior changes and explain any architecture decision that affects more than one layer.

The core should stay independent from specific providers. New integrations belong behind an existing contract or a new small contract with a clear reason to exist.
