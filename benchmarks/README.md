# Benchmarks

The benchmark suite measures repository retrieval behavior with real executions. It does not ship fabricated performance claims.

Run:

```bash
cortex benchmark --path . --cases benchmarks/cases.json --output benchmarks/results.json
```

The report records success rate, path and symbol recall, elapsed time, context tokens, files read, and tool calls for each strategy.

Use larger external repositories and task sets before publishing comparative numbers.
