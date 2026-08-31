# Security Policy

CodeCortex processes source code and may store local project state, traces, indexes, and benchmark artifacts. Treat those inputs and artifacts as potentially sensitive.

## Supported versions

During alpha, security fixes target the latest release and current `main`.

## Reporting a vulnerability

Do **not** open a public issue for suspected vulnerabilities. Use GitHub **Security → Report a vulnerability** / the private security-advisory flow. Include the affected version or commit, reproduction steps, impact, and suggested mitigation when known.

The project aims to acknowledge credible reports promptly, coordinate remediation privately, and publish an advisory after a fix is available when disclosure is appropriate.

## Security defaults

- Project state stays under `.codecortex/`.
- The dashboard binds to `127.0.0.1` by default.
- Core operation does not require a remote service.
- External adapters are disabled unless explicitly configured.
- Backend commands execute without a shell.
- Semantic edit paths are constrained to the project root.
- Task traces redact common credential/token fields.
- Agent configuration is merge-safe and refuses malformed configuration.
- Secrets should never be deliberately stored in project or team memory.

## Automated assurance

CI includes dependency auditing, Bandit, security-boundary tests, CodeQL, dependency review, OpenSSF Scorecard, coverage reporting, CycloneDX SBOM generation, signed release payloads, and build provenance attestations.

## Supply chain

Release artifacts include checksums and provenance. Consumers should verify release artifacts and avoid installing unreviewed forks or mutable source references in security-sensitive environments.
