#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PLASMA_PYTHON:-$project_dir/.venv/bin/python}"

if [[ ! -x "$python_bin" ]]; then
  printf 'Python test environment not found: %s\n' "$python_bin" >&2
  printf '%s\n' "Run: python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'" >&2
  exit 69
fi

cd "$project_dir"

"$python_bin" -m compileall -q \
  plasma_core \
  plasma_interfaces \
  plasma_handlers \
  plasma_server \
  plasma_client \
  tests

"$python_bin" -m pytest -q
