#!/usr/bin/env bash
set -Eeuo pipefail

script_path="$(readlink -f "${BASH_SOURCE[0]}")"
repo="$(cd "$(dirname "$script_path")/../.." && pwd)"
integration_test="$repo/scripts/tests/test-plasmactl-integration-config.sh"
integration_backend="${PLASMACTL_INTEGRATION_PATH:-$repo/scripts/plasmactl-integration}"

[[ -f "$integration_test" ]] || {
  printf '[plasmactl-test] FAIL: integration config test is missing: %s\n' "$integration_test" >&2
  exit 1
}
[[ -f "$integration_backend" ]] || {
  printf '[plasmactl-test] FAIL: integration backend is missing: %s\n' "$integration_backend" >&2
  exit 1
}

PLASMACTL_PATH="$integration_backend" bash "$integration_test"
