# Security Policy

CodeCortex reads source code, launches optional pinned backend processes, and stores local project state. Repository contents, memory, traces, indexes, and benchmark artifacts should be treated as potentially sensitive.

## Supported versions

Security fixes are applied to the latest release and the current `main` branch during alpha.

## Reporting a vulnerability

Please do **not** open a public issue for a suspected vulnerability.

Use the repository's GitHub **Security → Report a vulnerability** / private security-advisory flow so details remain private until a fix is available. Include the affected version or commit, reproduction steps, impact, and any suggested mitigation.

## Security defaults

- Project state stays under `.codecortex/`.
- The dashboard binds to `127.0.0.1` unless the user explicitly changes it.
- Core operation does not require a remote service.
- Backend commands are revision-pinned and executed without a shell.
- Semantic edit paths are resolved and constrained to the project root.
- Task traces redact common credential/token fields.
- Agent configuration is merge-safe, backed up before modification, and refuses malformed config files.
- Secrets should never be deliberately stored in project or team memory.

## Automated checks

Pull requests and `main` are checked with dependency auditing, Bandit, security boundary tests, CodeQL, dependency review, and CycloneDX SBOM generation.
