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
printf '%s\n' \
  'run_trace_coverage.sh is retained for compatibility; coverage now uses pytest-cov.'
"$python_bin" -m pytest -q \
  --cov=plasma_core \
  --cov=plasma_interfaces \
  --cov=plasma_handlers \
  --cov=plasma_server \
  --cov=plasma_client \
  --cov=plasma_web \
  --cov-report=term-missing
