# Platform administration

## Authentication

Local mode can run with the local administrator identity. Hosted deployments should set a bearer token and terminate TLS at the reverse proxy or ingress.

## Roles

- `viewer`: read intelligence and observability
- `member`: viewer access plus context and team memory workflows
- `admin`: member access plus repository, backend, worker and policy administration
- `owner`: organization ownership and role delegation

Workspace policy controls allowed tools, maximum context size and remote access.

## Mutations

Code edits and integration configuration require explicit approval. Code edits also bind approval to a SHA-256 hash of the previewed file, so a stale preview cannot be applied after the file changes.

## State

Local platform state uses SQLite/WAL under the configured platform state directory. Repository intelligence state remains in the repository `.codecortex` directory.

## Operations

Monitor `/api/v1/readiness`, `/api/v1/observability` and `/api/v1/metrics`. Use the Notification Center for failed jobs and backend degradation and the Audit Center for privileged operations.
