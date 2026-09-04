# Licensing and attribution

## CodeCortex

CodeCortex Context Engine is distributed under the Apache License, Version 2.0. The repository `LICENSE` file is the authoritative open-source license text for CodeCortex-covered material.

The project copyright notice identifies:

- Copyright 2026 Behnam Jalali

Apache-2.0 provides broad permissions to use, reproduce, modify, distribute, sublicense, and use the software commercially, subject to its conditions. In particular, redistributed derivatives must retain applicable notices and comply with the license's redistribution terms.

## Historical upstream lineage

Early architecture and integration work involved source lineage from three public projects. Their recorded revisions and licenses are maintained under `docs/provenance/` and summarized in `THIRD_PARTY_NOTICES.md`:

- Graphify — Apache-2.0 at the recorded revision.
- Serena — MIT at the recorded revision.
- Headroom — Apache-2.0 at the recorded revision.

Upstream copyright remains with the applicable upstream copyright holders. CodeCortex Git commits record the authorship of CodeCortex-specific integration and subsequent changes independently.

## Integrated protocols and optional dependencies

The evidence-fusion layers integrate three further public projects. None of them is vendored into this repository: one is consumed as a published protocol, one is reached as an optional remote service, and one is invoked as an optional external subprocess. Recorded revisions and licenses are maintained under `docs/provenance/` and summarized in `THIRD_PARTY_NOTICES.md`:

- SCIP Code Intelligence Protocol — Apache-2.0 at the recorded revision; consumed as a protocol.
- Context7 — MIT at the recorded revision; reached as an optional, disabled-by-default remote provider.
- ast-grep — MIT at the recorded revision; invoked as an optional external subprocess and declared as the `structural` extra.

CodeCortex does not present itself as a distribution of, or a wrapper around, any of these projects. Product-facing names in the CLI, MCP surface, dashboard, and documentation are CodeCortex-native; the upstream names appear in licensing and provenance records, where attribution belongs.

## NOTICE handling

The root `NOTICE` file includes CodeCortex's project notice and applicable upstream attribution. `THIRD_PARTY_NOTICES.md` preserves more detailed license and provenance context, including the Serena MIT text and upstream NOTICE information.

## Dependencies and release artifacts

Python dependencies are declared in `pyproject.toml`. Every release pipeline run generates a CycloneDX SBOM and cryptographic checksums. Signed release artifacts and provenance attestations are intended to let downstream users identify exactly what was shipped and audit dependency licensing against the relevant versions.

## Commercial arrangements

Apache-2.0 does not prevent the copyright holder from offering separate commercial support, warranties, hosted services, enterprise terms, or separately licensed material for rights the provider is authorized to grant. Any separate commercial agreement is distinct from the rights already granted under Apache-2.0 for Apache-covered material.

## Trademarks

Open-source copyright licenses do not automatically grant broad trademark rights. Names and marks belonging to third parties remain the property of their respective owners. Attribution in CodeCortex documentation is descriptive and does not imply endorsement or affiliation.
