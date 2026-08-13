#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
coverage_dir="$(mktemp -d)"

cleanup() {
  rm -rf "$coverage_dir"
}
trap cleanup EXIT

cd "$project_dir"
python3 -m trace \
  --count \
  --summary \
  --missing \
  --coverdir "$coverage_dir" \
  --ignore-dir=/usr:/opt \
  --module unittest discover -s tests
