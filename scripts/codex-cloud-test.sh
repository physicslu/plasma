#!/usr/bin/env bash
set -Eeuo pipefail

script_path="$(readlink -f "${BASH_SOURCE[0]}")"
repo="$(cd "$(dirname "$script_path")/.." && pwd)"
python_dir="$repo/software/python"
web_dir="$repo/software/web"
python_bin="$python_dir/.venv/bin/python"

if [[ ! -x "$python_bin" ]]; then
  printf '%s\n' \
    '[codex-cloud] ERROR: Python environment is missing.' \
    '[codex-cloud] Run: bash scripts/codex-cloud-setup.sh' >&2
  exit 69
fi

printf '[codex-cloud] Running deployment config migration test\n'
bash "$repo/scripts/tests/test-plasmactl-config.sh"

printf '[codex-cloud] Running Python and PL source tests with pytest\n'
(
  cd "$repo"
  "$python_bin" -m pytest -q software/python/tests pl/tests
)

if [[ ! -x "$web_dir/node_modules/.bin/vinext" ]]; then
  printf '%s\n' \
    '[codex-cloud] ERROR: Web dependencies are missing.' \
    '[codex-cloud] Run: bash scripts/codex-cloud-setup.sh' >&2
  exit 69
fi

printf '[codex-cloud] Running Web lint, tests, and artifact validation\n'
(
  cd "$web_dir"
  npm run lint
  npm test
  npm run validate:artifact
)

printf '%s\n' \
  '[codex-cloud] Software validation passed.' \
  '[codex-cloud] Not validated here: Vivado, SWPC services/deployment, Z2, FPGA I/O, or real IC programming.'
