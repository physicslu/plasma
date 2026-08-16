#!/usr/bin/env bash
set -Eeuo pipefail

script_path="$(readlink -f "${BASH_SOURCE[0]}")"
repo="$(cd "$(dirname "$script_path")/.." && pwd)"
python_dir="$repo/software/python"
web_dir="$repo/software/web"
python_cmd="${PLASMA_CLOUD_PYTHON:-python3}"
venv_python="$python_dir/.venv/bin/python"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[codex-cloud] ERROR: missing required command: %s\n' "$1" >&2
    exit 69
  }
}

require_command "$python_cmd"
require_command node
require_command npm

"$python_cmd" - <<'PY'
import sys

if sys.version_info < (3, 11):
    raise SystemExit(
        f"Plasma requires Python >= 3.11; found {sys.version.split()[0]}"
    )
print(f"[codex-cloud] Python {sys.version.split()[0]}")
PY

node --input-type=module <<'NODE'
const [major, minor] = process.versions.node.split(".").map(Number);
if (major < 22 || (major === 22 && minor < 13)) {
  throw new Error(`Plasma requires Node.js >= 22.13.0; found ${process.version}`);
}
console.log(`[codex-cloud] Node.js ${process.version}`);
NODE

if [[ ! -x "$venv_python" ]]; then
  printf '[codex-cloud] Creating Python virtual environment\n'
  "$python_cmd" -m venv "$python_dir/.venv"
fi

if ! "$venv_python" -m pip --version >/dev/null 2>&1; then
  "$venv_python" -m ensurepip --upgrade
fi

printf '[codex-cloud] Installing Python development dependencies\n'
"$venv_python" -m pip install --disable-pip-version-check -e "${python_dir}[dev]"

printf '[codex-cloud] Installing locked Web dependencies\n'
(
  cd "$web_dir"
  npm run install:ci
)

printf '[codex-cloud] Setup complete\n'
