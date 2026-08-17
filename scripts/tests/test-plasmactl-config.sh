#!/usr/bin/env bash
set -Eeuo pipefail

script_path="$(readlink -f "${BASH_SOURCE[0]}")"
repo="$(cd "$(dirname "$script_path")/../.." && pwd)"
plasmactl_path="${PLASMACTL_PATH:-$repo/scripts/plasmactl}"
temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT

fail() {
  printf '[plasmactl-test] FAIL: %s\n' "$*" >&2
  exit 1
}

assert_file_line() {
  local file="$1" expected="$2"
  grep -Fxq "$expected" "$file" || fail "$file missing: $expected"
}

run_migration_case() {
  local name="$1" initial="$2" expected_url="$3" expected_version="$4"
  local config="$temporary/$name.env" output
  printf '%s\n' "$initial" >"$config"

  output="$({
    PLASMACTL_LIB_ONLY=1 \
    PLASMACTL_CONFIG="$config" \
    XDG_CONFIG_HOME="$temporary/xdg-$name" \
    bash -c 'source "$1"; migrate_config; printf "%s\n" "$public_api_url"' _ "$plasmactl_path"
  })"

  [[ "${output##*$'\n'}" == "$expected_url" ]] || fail "$name resolved URL mismatch: $output"
  assert_file_line "$config" "PLASMA_CONFIG_VERSION=$expected_version"
  assert_file_line "$config" "PLASMA_PUBLIC_API_URL=$expected_url"
}

run_migration_case \
  legacy-tailscale \
  'PLASMA_PUBLIC_API_URL=https://swpc.tail820e64.ts.net:8443' \
  'https://plasma.open4th.com' \
  '2'

run_migration_case \
  legacy-localhost \
  'PLASMA_PUBLIC_API_URL=http://127.0.0.1:8080' \
  'https://plasma.open4th.com' \
  '2'

run_migration_case \
  custom-override \
  'PLASMA_PUBLIC_API_URL=https://lab-api.example.invalid' \
  'https://lab-api.example.invalid' \
  '2'

run_migration_case \
  already-v2 \
  $'PLASMA_CONFIG_VERSION=2\nPLASMA_PUBLIC_API_URL=https://swpc.tail820e64.ts.net:8443' \
  'https://swpc.tail820e64.ts.net:8443' \
  '2'

new_config="$temporary/new.env"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$new_config" \
XDG_CONFIG_HOME="$temporary/xdg-new" \
bash -c 'source "$1"; write_config' _ "$plasmactl_path" >/dev/null
assert_file_line "$new_config" 'PLASMA_CONFIG_VERSION=2'
assert_file_line "$new_config" 'PLASMA_PUBLIC_API_URL=https://plasma.open4th.com'

grep -Fq 'PLASMACTL_DEPLOY_REEXEC=1 exec "$script_path" deploy' "$plasmactl_path" || fail 'deploy does not re-exec updated plasmactl'
grep -Fq 'reconcile_service_units' "$plasmactl_path" || fail 'service-unit reconciliation is missing'

printf '[plasmactl-test] PASS\n'
