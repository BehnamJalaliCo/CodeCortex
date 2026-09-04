# Definition of Done

A CodeCortex Platform feature is not complete because a screen renders or an endpoint returns `200`.

Every feature must satisfy the machine-readable checklist in `platform/definition_of_done.json`: core implementation, tests, API contract, authorization, audit decision, error handling, loading and empty states, responsive UI when applicable, documentation, passing CI, and no known regression.

For backend-only features, UI-specific checks are still decisions: set them true only after documenting that the feature has no user-facing UI requirement or after the relevant presentation state exists.

Use `scripts/check_feature_done.py <feature-completion.json>` to validate a release artifact or feature handoff.
