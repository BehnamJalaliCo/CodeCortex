# SWE-bench Verified A/B

This benchmark measures the effect of CodeCortex on the same coding agent.

## Fairness contract

Both arms use:

- the same SWE-bench Verified task;
- the same repository base commit;
- the same Codex CLI version;
- the same OpenAI model and reasoning effort;
- the same issue prompt and GitHub-hosted runner class.

The only intended difference is:

- **baseline**: Codex without CodeCortex;
- **codecortex**: Codex with the CodeCortex MCP server and a prebuilt local index.

The inference prompt forbids web lookup, original-PR lookup, and gold/reference-patch lookup. The SWE-bench gold patch and test patch are never written into the agent workspace.

## First validation run

Start with one task:

`["sympy__sympy-20590"]`

This is a pipeline validation, not a statistical claim. Increase the task set only after both arms produce valid prediction artifacts.

## Required GitHub Actions secrets

- `OPENAI_API_KEY` — used only by the official OpenAI Codex GitHub Action.
- `SWEBENCH_API_KEY` — used only when `submit_cloud_eval=true`.

Never commit either secret.

## Evidence

Each arm uploads:

- SWE-bench prediction JSON;
- patch SHA-256 and patch size;
- exact repository/base commit;
- CodeCortex repository commit;
- model and reasoning effort;
- Git status;
- observed CodeCortex MCP tool-call counts;
- the final Codex message.

The combine job creates:

- `predictions-baseline.json`;
- `predictions-codecortex.json`;
- `summary.json`.

When cloud evaluation is enabled, both prediction files are submitted separately to the official SWE-bench cloud evaluator with distinct run IDs.
