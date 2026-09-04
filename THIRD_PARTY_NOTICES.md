# Third-Party Notices

CodeCortex itself is distributed under the Apache License, Version 2.0. This file records third-party and historical upstream lineage that informed or was integrated during the project's development. It supplements, and does not replace, the repository `LICENSE` and `NOTICE` files.

## Graphify

- Project: Graphify
- Repository: https://github.com/Graphify-Labs/graphify
- Recorded revision: `33362d969292b57eda82f3fbd9eb5f3f5bc9bbc2`
- License at the recorded revision: Apache License 2.0
- Upstream notice at the recorded revision:

> Graphify  
> Copyright 2026 Safi Shamsi and the Graphify contributors.  
> This product is licensed under the Apache License, Version 2.0.  
> Portions of this software were contributed under the MIT License prior to relicensing; the upstream project retains the original MIT license text.

The complete Apache-2.0 terms are available in CodeCortex's `LICENSE` file and in the upstream repository. The recorded provenance is also stored in `docs/provenance/graphify.md`.

## Serena

- Project: Serena
- Repository: https://github.com/oraios/serena
- Recorded revision: `43ae0211d7f3bba4101cd0552707fa21d37f4c84`
- License at the recorded revision: MIT License
- Copyright notice: Copyright (c) 2025 Oraios AI

### Serena MIT License

MIT License

Copyright (c) 2025 Oraios AI

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

The recorded provenance is also stored in `docs/provenance/serena.md`.

## Headroom

- Project: Headroom
- Repository: https://github.com/headroomlabs-ai/headroom
- Recorded revision: `a811984ffb62a866274dda2928f78922101c824b`
- License at the recorded revision: Apache License 2.0
- Copyright notice: Copyright 2025 Headroom Contributors

The upstream NOTICE at the recorded revision also identifies these dependencies used by Headroom: tiktoken (MIT), Pydantic (MIT), sentence-transformers (Apache-2.0, optional), FastAPI (MIT, optional), NumPy (BSD-3-Clause, optional), Tailwind CSS (MIT), htmx (0BSD), and Alpine.js (MIT). Those entries describe Headroom's distribution and are retained here as upstream attribution context; they do not by themselves assert that every listed dependency is bundled by CodeCortex.

The complete Apache-2.0 terms are available in CodeCortex's `LICENSE` file and in the upstream repository. The recorded provenance is also stored in `docs/provenance/headroom.md`.

## SCIP Code Intelligence Protocol

- Project: SCIP
- Repository: https://github.com/scip-code/scip
- Recorded revision: `1c2b6db7e560d5233c944f36e4ac1377cc6963fc`
- License at the recorded revision: Apache License 2.0
- Integration mode: protocol consumption. CodeCortex implements an original
  reader for the published index schema and symbol-identity grammar. No
  upstream implementation source code is copied into the shipped package.

### Vendored schema fixture

One upstream file is vendored, as a test fixture only:

| Local path | Upstream path | Modifications |
| --- | --- | --- |
| `tests/fixtures/upstream/scip/scip.proto` | `scip.proto` | none — byte-identical |
| `tests/fixtures/upstream/scip/LICENSE` | `LICENSE` | none — byte-identical |

The schema is vendored so that `tests/test_precision_conformance.py` can verify
CodeCortex's transcribed field numbers against the authoritative definition
deterministically and offline. It is not imported by `src/codecortex`, is not
included in the built wheel, and is not a runtime dependency. Exact digests and
the upstream URLs are recorded in
`tests/fixtures/upstream/scip/PROVENANCE.json`.

The complete Apache-2.0 terms are available in CodeCortex's `LICENSE` file, in
`tests/fixtures/upstream/scip/LICENSE`, and in the upstream repository. The
recorded provenance is also stored in
`docs/provenance/precision-intelligence.md`.

## Context7

- Project: Context7
- Repository: https://github.com/upstash/context7
- Recorded revision: `a37d30cf14f69341e12c226fcc729c62b4f0a900`
- License at the recorded revision: MIT License
- Copyright notice: Copyright (c) 2021 Upstash, Inc.
- Integration mode: remote service adapter behind an optional, disabled-by-default
  provider interface. No upstream source code is copied or vendored.

Note on self-hosting: the upstream public repository contains the client-facing
packages, and its own documentation states that supporting backend, parsing, and
crawling components are not part of that public repository. CodeCortex therefore
does not claim offline or self-hosted parity for this capability. See
`docs/provenance/dependency-documentation.md`.

### Context7 MIT License

MIT License

Copyright (c) 2021 Upstash, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## ast-grep

- Project: ast-grep
- Repository: https://github.com/ast-grep/ast-grep
- Recorded revision: `29285d16757371a70a93190929940886e68618d3`
- Version tested against: `0.45.3` (`ast-grep-cli`)
- License at the recorded revision: MIT License
- Copyright notice: Copyright (c) 2022 Herrington Darkholme
- Integration mode: optional external dependency invoked as a subprocess and
  declared as the `structural` extra. No upstream source code is copied or
  vendored, and CodeCortex Core does not require it.

### ast-grep MIT License

MIT License

Copyright (c) 2022 Herrington Darkholme

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

The recorded provenance is also stored in `docs/provenance/structural-intelligence.md`.

## defusedxml

- Project: defusedxml
- Repository: https://github.com/tiran/defusedxml
- License: Python Software Foundation License
- Integration mode: direct runtime dependency. Used to refuse document type and
  entity declarations when parsing XML build manifests, so a hostile manifest
  cannot trigger entity expansion or external entity disclosure.

## CodeCortex dependency licensing

CodeCortex's own direct Python dependencies are declared in `pyproject.toml`. Dependency licenses can change between versions; release SBOMs are generated by the release pipeline so consumers can audit the exact dependency graph for a published artifact.

## Scope

These notices preserve source lineage and attribution. They do not imply endorsement, affiliation, trademark permission, copyright transfer, or that upstream authors are responsible for CodeCortex modifications. CodeCortex-specific code, integration work, packaging, tests, documentation, and subsequent changes are tracked in this repository's own Git history.
