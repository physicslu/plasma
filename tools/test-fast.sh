#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_DIR="$ROOT_DIR/software/python"
WEB_DIR="$ROOT_DIR/software/web"
PYTHON_BIN="$PYTHON_DIR/.venv/bin/python"

section() {
  printf '\n==> %s\n' "$1"
}

fail() {
  printf '\nERROR: %s\n' "$1" >&2
  exit 1
}

cd "$ROOT_DIR"

section "Plasma fast validation"
printf 'Repository: %s\n' "$ROOT_DIR"
printf 'Branch:     %s\n' "$(git branch --show-current 2>/dev/null || printf unknown)"
printf 'Commit:     %s\n' "$(git rev-parse --short HEAD 2>/dev/null || printf unknown)"

[[ -x "$PYTHON_BIN" ]] || fail "Python venv is missing at $PYTHON_BIN. Do not install packages automatically; prepare the documented development environment first."

section "Python unit + integration + Mock E2E tests"
(
  cd "$PYTHON_DIR"
  "$PYTHON_BIN" -m pytest -q
)

section "Web toolchain"
if ! command -v node >/dev/null 2>&1; then
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [[ -s "$NVM_DIR/nvm.sh" ]]; then
    # shellcheck disable=SC1090
    source "$NVM_DIR/nvm.sh"
  fi
fi
command -v node >/dev/null 2>&1 || fail "Node.js is not available. Expected Node >= 22.13.0."
command -v npm >/dev/null 2>&1 || fail "npm is not available."
node -e 'const [a,b]=process.versions.node.split(".").map(Number); if (a < 22 || (a === 22 && b < 13)) { console.error(`Node ${process.versions.node} is too old; require >=22.13.0`); process.exit(1); }'
[[ -d "$WEB_DIR/node_modules" ]] || fail "software/web/node_modules is missing. This script never installs dependencies automatically."

section "Web lint"
(
  cd "$WEB_DIR"
  npm run lint
)

section "Web build + tests"
(
  cd "$WEB_DIR"
  npm test
)

section "Web artifact validation"
(
  cd "$WEB_DIR"
  npm run validate:artifact
)

if [[ -d "$ROOT_DIR/pl/tests" ]]; then
  section "FPGA repository tests (no Vivado required)"
  command -v python3 >/dev/null 2>&1 || fail "python3 is required for pl/tests."
  (
    cd "$ROOT_DIR"
    python3 -m unittest discover -s pl/tests -v
  )
fi

section "PASS"
printf '%s\n' \
  "Python tests: PASS (includes Mock Web/Python E2E)" \
  "Web lint/build/tests/artifact: PASS" \
  "FPGA repository tests: PASS" \
  "No services were started/stopped and no dependencies were installed."
