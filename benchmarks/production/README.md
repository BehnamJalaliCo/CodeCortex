# Production Benchmarks

This suite uses immutable revisions of real public repositories. It is designed to produce evidence, not marketing numbers.

## Engine-level matrix

```bash
python scripts/run_production_benchmark.py --provision
```

Scenarios:

- `vanilla`: full-repository lexical scan.
- `graph`: repository graph backend only.
- `symbols`: semantic symbol backend only.
- `context`: the vanilla evidence passed through the context optimizer. This isolates compression/preservation because a context optimizer is not itself a retrieval engine.
- `full`: graph + semantic symbol retrieval + context optimization under the CodeCortex integration path.

Measured fields include wall time, context characters, estimated context tokens, files surfaced, tool calls, path recall and symbol recall. `files_read` is recorded only when the runner can observe it. Provider input/output tokens and cost are never guessed.

## Real-agent matrix

To compare an actual coding agent under the five scenarios:

```bash
python scripts/run_agent_matrix.py --command "./my-instrumented-agent"
```

The command receives one JSON object on stdin:

```json
{
  "schema_version": 1,
  "scenario": "full",
  "repository": "/absolute/path/to/repo",
  "case": {
    "id": "api-router",
    "query": "APIRouter",
    "expected_paths": ["fastapi/routing.py"],
    "expected_symbols": ["APIRouter"]
  }
}
```

It must return JSON containing `answer`. It may also report observed `files_read`, `tool_calls`, `input_tokens`, `output_tokens`, `cost_usd`, and `cost_source`. Missing values remain `null` in results.

Benchmark result JSON is generated at runtime and is not committed as proof until it has been produced by a reproducible run.
