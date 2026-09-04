# Dependency Documentation provenance record

CodeCortex's Dependency Intelligence layer reads dependency manifests locally
and, when a project explicitly enables it, retrieves version-aware
documentation from a hosted third-party service through a provider interface.

## Upstream source

- Upstream project: Context7
- Upstream repository: `upstash/context7`
- Upstream URL: https://github.com/upstash/context7
- Recorded upstream branch: `main` (informational only)
- Recorded upstream commit: `a37d30cf14f69341e12c226fcc729c62b4f0a900`
- License observed at the recorded revision: MIT License
- Copyright notice at the recorded revision: Copyright (c) 2021 Upstash, Inc.

## Integration mode

**Remote service adapter.** No upstream source code is copied into CodeCortex.

`src/codecortex/dependencies/remote.py` is an original HTTP client written
against the request shape used by the upstream client at the recorded revision:
a library search endpoint and a documentation-context endpoint, with bearer
authentication. It is one implementation of the
`DependencyDocumentationProvider` contract; any other provider can be supplied
instead, and the deterministic fake used in CodeCortex's tests is one.

## Self-hosting: an explicit limitation

The upstream public repository contains the client, MCP, SDK, and CLI packages.
Its own documentation states that supporting backend, parsing, and crawling
components are **not** part of the public repository. CodeCortex therefore does
not claim, and must not be described as offering, full offline or self-hosted
parity for this capability.

Consequences enforced in the code:

- the capability is **disabled by default** and must be enabled per project;
- an API key is read only from a configured environment variable, never from
  project state, and is redacted from diagnostics and telemetry;
- CodeCortex Core operates fully with no network access; when the provider is
  unavailable the dependency layer returns local manifest facts plus an
  explicit docs-unavailable state, and never fabricates documentation;
- CodeCortex's own tests never contact the service. They use deterministic
  fakes and a local HTTP stub, so CI requires no account and no credentials.

## Privacy boundary

Requests carry only the dependency name, the resolved version, and the user's
question. Source files, file paths, secrets, environment contents, Git history,
and memory are never transmitted. This boundary is asserted by a test that
inspects the outgoing request parameters.

## What this record does not claim

This record does not imply endorsement by, affiliation with, or sponsorship
from the upstream project or Upstash, Inc., and it does not transfer any
copyright. CodeCortex's manifest parsers, resolver, provider contract, cache,
fallback behavior, MCP tools, CLI, and tests are original work governed by this
repository's own license and history.
