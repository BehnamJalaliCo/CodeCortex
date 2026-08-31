# Packaging

The public product remains **CodeCortex** and the primary executable remains `cortex`.

The Python distribution is **`codecortex-context-engine`**. A distinct distribution name is intentional because multiple unrelated projects already occupy shorter CodeCortex-like names on package registries.

After the first published release:

```bash
uv tool install codecortex-context-engine
# or
pipx install codecortex-context-engine
```

The Python import remains `codecortex` and the console executables remain `cortex` and `codecortex`.

Release artifacts are checksumed, Sigstore-signed, and receive GitHub build-provenance attestations. Container images are published separately to GHCR.
