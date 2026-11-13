#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_dir="${repo_root}/software/python"
web_dir="${repo_root}/software/web"
export PLASMA_REQUIRE_BUILD_IDENTITY=1
diagnose_identity() {
  python "${repo_root}/scripts/render-build-identity-diagnostic.py" "$1"
}

diagnose_identity before-python
printf '[render-build] Installing Plasma Python runtime dependencies\n'
python -m pip install --disable-pip-version-check "${python_dir}"
diagnose_identity after-python

diagnose_identity before-npm
printf '[render-build] Installing locked Web build dependencies\n'
npm run install:ci --prefix "${web_dir}"
diagnose_identity after-npm

diagnose_identity before-vinext
printf '[render-build] Building source-tree-independent Control Station Console/BFF runtime\n'
npm run build:product --prefix "${web_dir}"
test -f "${web_dir}/dist/standalone/server.js"
diagnose_identity after-artifact

printf '[render-build] Render Control Station runtime is ready\n'
