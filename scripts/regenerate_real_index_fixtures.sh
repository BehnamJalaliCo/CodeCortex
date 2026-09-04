#!/usr/bin/env bash
# Regenerate the committed real-index conformance fixtures.
#
# This is not part of normal CI. The generated index.scip and expected.json are
# committed so that conformance tests run offline; this script exists so the
# generation is reproducible and the pins are visible in one place.
#
# It builds three tools from source at exact revisions:
#   - the official CLI, used only as an independent oracle (scip lint / print)
#   - the pinned Python indexer
#   - the pinned TypeScript indexer
# None of them is a CodeCortex runtime dependency, and no upstream source is
# vendored into the package.
#
# Requires: git, go >= 1.25, node, npm, yarn.
set -euo pipefail

SCIP_COMMIT=1c2b6db7e560d5233c944f36e4ac1377cc6963fc
SCIP_PYTHON_COMMIT=8b60bbce1f2a4c7a517776cb395bbafb2e731e4f
SCIP_TYPESCRIPT_COMMIT=891eb4293709a6a587bf4468dfa1b45a85182fd9

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURES="${REPO_ROOT}/tests/fixtures/real_index"
WORK="${WORK_DIR:-$(mktemp -d)}"
# A stable generation root: it is recorded verbatim in Metadata.project_root,
# so a per-run temporary path would churn the committed fixtures every time.
GENERATION_ROOT=/tmp/codecortex-fixture

echo "==> building tools in ${WORK}"
mkdir -p "${WORK}/bin"

git clone --filter=blob:none --quiet https://github.com/scip-code/scip.git "${WORK}/scip"
git -C "${WORK}/scip" checkout --quiet "${SCIP_COMMIT}"
(cd "${WORK}/scip" && GOTOOLCHAIN=auto go build -o "${WORK}/bin/scip" ./cmd/scip)

git clone --filter=blob:none --quiet https://github.com/sourcegraph/scip-python.git "${WORK}/scip-python"
git -C "${WORK}/scip-python" checkout --quiet "${SCIP_PYTHON_COMMIT}"
(cd "${WORK}/scip-python" && npm ci --no-audit --no-fund --silent)
(cd "${WORK}/scip-python/packages/pyright-scip" && npm ci --no-audit --no-fund --silent && npm run --silent build)
SCIP_PYTHON="${WORK}/scip-python/packages/pyright-scip/dist/scip-python.js"

git clone --filter=blob:none --quiet https://github.com/sourcegraph/scip-typescript.git "${WORK}/scip-typescript"
git -C "${WORK}/scip-typescript" checkout --quiet "${SCIP_TYPESCRIPT_COMMIT}"
(cd "${WORK}/scip-typescript" && yarn install --frozen-lockfile --silent && yarn --silent build)
SCIP_TYPESCRIPT="${WORK}/scip-typescript/dist/src/main.js"

echo "==> generating indexes from ${GENERATION_ROOT}"
rm -rf "${GENERATION_ROOT}"
mkdir -p "${GENERATION_ROOT}/python" "${GENERATION_ROOT}/typescript"
cp -r "${FIXTURES}/python_project/app" "${GENERATION_ROOT}/python/"
cp -r "${FIXTURES}/typescript_project/src" "${GENERATION_ROOT}/typescript/"
cp "${FIXTURES}/typescript_project/package.json" "${FIXTURES}/typescript_project/tsconfig.json" \
  "${GENERATION_ROOT}/typescript/"

(cd "${GENERATION_ROOT}/python" && node "${SCIP_PYTHON}" index . \
  --project-name=codecortex-python-fixture --project-version=1.0.0)
(cd "${GENERATION_ROOT}/typescript" && node "${SCIP_TYPESCRIPT}" index --no-progress-bar)

echo "==> validating with the official CLI"
"${WORK}/bin/scip" lint "${GENERATION_ROOT}/python/index.scip"
"${WORK}/bin/scip" lint "${GENERATION_ROOT}/typescript/index.scip"

echo "==> updating committed fixtures"
cp "${GENERATION_ROOT}/python/index.scip" "${FIXTURES}/python_project/index.scip"
cp "${GENERATION_ROOT}/typescript/index.scip" "${FIXTURES}/typescript_project/index.scip"
"${WORK}/bin/scip" print --json "${GENERATION_ROOT}/python/index.scip" \
  > "${FIXTURES}/python_project/expected.json"
"${WORK}/bin/scip" print --json "${GENERATION_ROOT}/typescript/index.scip" \
  > "${FIXTURES}/typescript_project/expected.json"

echo "==> refreshing provenance manifests"
python3 "${REPO_ROOT}/scripts/write_real_index_provenance.py"

echo "done. Review the diff, then run: pytest -q tests/test_real_index_conformance.py"
