# API compatibility policy

`/api/v1` is the first stable CodeCortex Platform HTTP contract.

Rules:

1. Existing fields and endpoints in a stable version are not removed or redefined incompatibly.
2. Additive optional fields and new endpoints may be added to the same stable version.
3. A breaking request or response change requires a new prefix such as `/api/v2`.
4. Deprecated versions remain discoverable through `/api/v1/api-versions` while supported.
5. SDKs default to the current stable version but allow the caller to select a version explicitly.
