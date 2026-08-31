# OpenSSF Readiness

CodeCortex is structured to pursue both the OpenSSF Best Practices metal-series badge and the OSPS Baseline badge.

## Repository evidence already present

- Public version-controlled source and issue tracker.
- Apache-2.0 license.
- Contribution, governance, support, security, and conduct policies.
- Automated tests across supported Python versions.
- Dependency auditing, CodeQL, Bandit, SBOM generation, Scorecard, and release provenance.
- Private vulnerability-reporting instructions.
- Reproducible release workflow with checksums, signing, and attestations.

## External enrollment

The badge itself is issued by the OpenSSF Best Practices web service and requires the project owner to authenticate and register the repository. The official service can auto-populate many criteria from this repository. Start with OSPS Baseline level 1, then complete the metal-series Passing badge, followed by Silver and Gold as the project matures.

Do not display an OpenSSF Best Practices badge in the README until the external service has issued a real project ID and status.

## Repository administration still required

Configure a GitHub ruleset for `main` requiring pull requests, required CI/security checks, conversation resolution, and protection against deletion and force-push. Repository-administration controls cannot be represented truthfully by files alone; they must be enabled in GitHub settings.
