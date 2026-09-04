# Platform architecture invariants

These rules are enforced rather than left as design notes.

- The React Console never opens SQLite, repository state files, or Python engines directly.
- The legacy `dashboard.py` remains a local compatibility surface and is not the hosted platform.
- Built-in repository and symbol engines do not reintroduce full `ProjectIndexer` rebuilds per request.
- Product metrics are measured, estimated, or unavailable; fake metric constants are prohibited.
- The hosted interface uses the versioned HTTP layer and shared application services instead of duplicating repository intelligence in the browser.
- Local mode must remain service-free: PostgreSQL, Redis, and external vector databases are optional server-mode choices, never installation requirements.
- Mutating features must retain explicit approval and audit boundaries.
