# Benchmarks and Evidence

CodeCortex treats benchmark results as evidence with a scope, revision, methodology, and limitations. Numbers are not generalized beyond what was actually measured.

## Current committed evidence

The Evidence Fusion hardening report records:

| Measurement | Recorded result |
|---|---:|
| Hardening test suite | 711 passed, 28 skipped, 0 failed |
| Repository coverage | 91.74% |
| Cold real-index import | Python 0.93 ms / TypeScript 0.99 ms median |
| Warm exact definition lookup | 0.19–0.23 ms median |
| Warm exact reference lookup | 0.29–0.33 ms median |
| Unicode caret navigation | 0.18–0.32 ms median |
| Freshness scan, 600 documents | 4.25 ms median |

These values are hardening-specific measurements on committed fixtures and indexes. They are not promises for arbitrary repositories or machines.

## Evidence-quality benchmark

The same report records three bounded fixture cases:

| Case | Baseline strategy | Evidence strategy |
|---|---|---|
| Duplicate symbols | graph heuristic precision 0.50 | precision index 1.00 |
| Dependency version | source-only 0.00 | dependency intelligence 1.00 |
| Mechanical migration | lexical scan 0.50 | structural search 1.00 |

The purpose is to demonstrate which evidence layer resolves each controlled ambiguity. It is not a claim that every real-world task improves by the same amount.

## Reproduce local benchmark runs

```bash
cortex benchmark --path . --cases benchmarks/cases.json --output benchmarks/results.json
```

Production benchmark tooling uses revision-pinned public repositories:

```bash
python scripts/run_production_benchmark.py --provision
```

See [benchmarks/README.md](../benchmarks/README.md) and [benchmarks/production/README.md](../benchmarks/production/README.md) in the repository for the exact harness and output fields.

## Real-agent measurements

For an instrumented coding-agent command:

```bash
python scripts/run_agent_matrix.py --command "./my-instrumented-agent"
```

Missing provider token counts, cost, files-read telemetry, or other unobserved metrics remain missing. CodeCortex does not infer or invent them.

## Known unavailable evidence

The live dependency-documentation provider remains credential-gated. The hardening report explicitly records its live smoke path as skipped when no credential is configured. Do not interpret that skip as a successful live validation.

## Source of record

For current evidence and caveats, read:

- [HARDENING_REPORT.md](../HARDENING_REPORT.md)
- [Quality targets](QUALITY.md)
- [Testing](TESTING.md)
- [Release evidence](RELEASE.md)
