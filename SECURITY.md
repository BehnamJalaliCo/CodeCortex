# Security

CodeCortex reads source code and stores local project state. Treat repository contents, memory, logs, and indexes as potentially sensitive data.

## Defaults

- Project state stays under `.codecortex/`.
- The dashboard binds to `127.0.0.1` by default.
- The core does not require a remote service.
- Secrets should never be stored in project memory or telemetry.

For a security issue, please avoid opening a public issue until a private reporting channel is published for the project.
