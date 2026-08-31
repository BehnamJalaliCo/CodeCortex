# Third-Party Backends

CodeCortex can provision optional open-source backend engines in isolated virtual environments. Their source code is not vendored into the CodeCortex package; installations are pinned to specific upstream revisions and remain subject to their own licenses and notices.

| Backend role | Project | Revision | License |
|---|---|---|---|
| Repository graph intelligence | Graphify-Labs/graphify | `33362d969292b57eda82f3fbd9eb5f3f5bc9bbc2` | Apache-2.0 (with upstream NOTICE/license files) |
| Semantic symbol intelligence | oraios/serena | `43ae0211d7f3bba4101cd0552707fa21d37f4c84` | MIT |
| Context optimization | headroomlabs-ai/headroom | `65477f933a775bd519d4b037d31d93b3e255e297` | Apache-2.0 |

When a backend is provisioned, its complete package, license files, notices and transitive dependencies live in its isolated environment. CodeCortex does not remove, rewrite or replace upstream copyright, attribution, NOTICE or license material.

The pinned revisions are compatibility inputs, not claims of ownership. CodeCortex-owned code is the orchestration, routing, stable adapter boundary, unified memory, workspace intelligence, change intelligence, tracing, evaluation and product integration layers in this repository.
