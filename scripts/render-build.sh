#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_dir="${repo_root}/software/python"
web_dir="${repo_root}/software/web"

printf '[render-build] Installing Plasma Python runtime dependencies\n'
python -m pip install --disable-pip-version-check "${python_dir}"

printf '[render-build] Installing locked Web build dependencies\n'
npm run install:ci --prefix "${web_dir}"

printf '[render-build] Building existing Plasma React pages as static assets\n'
npm run build:render --prefix "${web_dir}"

test -f "${web_dir}/dist-render/index.html"
printf '[render-build] Static Plasma Web Console is ready\n'
