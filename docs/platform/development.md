# Platform development

## Architecture rule

New product behavior belongs in the application/core layers. HTTP, MCP and CLI are adapters. Do not put repository intelligence logic in React or transport handlers.

## Adding an API feature

Optional feature routes live under `codecortex.api.routes`. The feature loader mounts a feature module when it exposes `mount(app, context)`. A missing optional feature module does not break the core API.

## Frontend

The Console lives in `web/`. Run `npm run typecheck`, `npm run build` and `npm run test:e2e` before merging UI changes.

## Testing

Python changes must keep the existing invariant/security suites passing and preserve the repository coverage threshold. New API behavior needs contract tests. Security-sensitive mutations need denial, stale-state and audit tests.

## Metrics

Never fabricate a metric. A metric is `measured`, `estimated` or `unavailable`. Benchmark and Quality Center output follows this rule.
