#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

python3 -m compileall -q \
  plasma_core \
  plasma_interfaces \
  plasma_handlers \
  plasma_server \
  plasma_client \
  tests

python3 -m unittest discover -s tests -v
