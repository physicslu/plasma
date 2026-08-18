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

resolve_default_public_api_url() {
  PLASMACTL_LIB_ONLY=1 \
  PLASMACTL_CONFIG="$temporary/no-config.env" \
  XDG_CONFIG_HOME="$temporary/xdg-default" \
  bash -c 'source "$1"; printf "%s\n" "$default_public_api_url"' _ "$plasmactl_path"
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

default_public_api_url="$(resolve_default_public_api_url)"
[[ "$default_public_api_url" =~ ^https?:// ]] || fail "default public API URL is invalid: $default_public_api_url"

run_migration_case \
  legacy-tailscale \
  'PLASMA_PUBLIC_API_URL=https://swpc.tail820e64.ts.net:8443' \
  "$default_public_api_url" \
  '2'

run_migration_case \
  legacy-localhost \
  'PLASMA_PUBLIC_API_URL=http://127.0.0.1:8080' \
  "$default_public_api_url" \
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
assert_file_line "$new_config" "PLASMA_PUBLIC_API_URL=$default_public_api_url"

unit_config="$temporary/unit-migration.env"
printf '%s\n' 'PLASMA_PUBLIC_API_URL=https://swpc.tail820e64.ts.net:8443' >"$unit_config"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$unit_config" \
XDG_CONFIG_HOME="$temporary/xdg-unit" \
bash -c 'source "$1"; migrate_config; write_units' _ "$plasmactl_path" >/dev/null
assert_file_line \
  "$temporary/xdg-unit/systemd/user/plasma-vite.service" \
  "Environment=NEXT_PUBLIC_PLASMA_API_URL=$default_public_api_url"

# The endpoint is configuration, not a fixed product constant. A valid explicit
# site value must survive schema handling and propagate unchanged into the
# generated runtime unit.
custom_runtime_url='https://programmer.customer.example.invalid'
custom_unit_config="$temporary/unit-custom.env"
printf '%s\n' \
  'PLASMA_CONFIG_VERSION=2' \
  "PLASMA_PUBLIC_API_URL=$custom_runtime_url" \
  >"$custom_unit_config"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$custom_unit_config" \
XDG_CONFIG_HOME="$temporary/xdg-custom-unit" \
bash -c 'source "$1"; migrate_config; write_units' _ "$plasmactl_path" >/dev/null
assert_file_line "$custom_unit_config" 'PLASMA_CONFIG_VERSION=2'
assert_file_line "$custom_unit_config" "PLASMA_PUBLIC_API_URL=$custom_runtime_url"
assert_file_line \
  "$temporary/xdg-custom-unit/systemd/user/plasma-vite.service" \
  "Environment=NEXT_PUBLIC_PLASMA_API_URL=$custom_runtime_url"

grep -Fq 'PLASMACTL_DEPLOY_REEXEC=1 exec "$script_path" deploy' "$plasmactl_path" || fail 'deploy does not re-exec updated plasmactl'
grep -Fq 'reconcile_service_units' "$plasmactl_path" || fail 'service-unit reconciliation is missing'

# Web deployment hygiene: source changes make a long-running Vite runtime stale,
# but package metadata alone must not cause npm ci under the live dev server.
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$temporary/no-hygiene-config.env" \
PLASMA_PYTHON="$(command -v python3)" \
XDG_CONFIG_HOME="$temporary/xdg-hygiene" \
bash -c '
  set -Eeuo pipefail
  source "$1"
  web_runtime_changed "software/web/app/page.tsx" || exit 11
  web_runtime_changed "software/python/plasma_core/config.py" && exit 12
  web_dependencies_changed "software/web/package.json" && exit 13
  web_dependencies_changed "software/web/package-lock.json" || exit 14
  web_manifest_matches_lock || exit 15
' _ "$plasmactl_path" || fail 'Web runtime/dependency classification contract failed'

# A targeted Web recovery must reconcile the unit, restart only Vite, then
# execute the Web health check. It must not bounce the programming server or
# REST Gateway.
web_restart_calls="$temporary/web-restart-calls.txt"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$temporary/no-restart-config.env" \
PLASMA_PYTHON="$(command -v python3)" \
XDG_CONFIG_HOME="$temporary/xdg-restart" \
PLASMACTL_TEST_CALLS="$web_restart_calls" \
bash -c '
  set -Eeuo pipefail
  source "$1"
  require_repo() { :; }
  require_runtime() { :; }
  reconcile_service_units() { printf "reconcile\n" >>"$PLASMACTL_TEST_CALLS"; }
  systemctl() { printf "systemctl %s\n" "$*" >>"$PLASMACTL_TEST_CALLS"; }
  web_health_check() { printf "web-health\n" >>"$PLASMACTL_TEST_CALLS"; }
  restart_web_console >/dev/null
' _ "$plasmactl_path" || fail 'web-restart execution contract failed'
assert_file_line "$web_restart_calls" 'reconcile'
assert_file_line "$web_restart_calls" 'systemctl --user restart plasma-vite.service'
assert_file_line "$web_restart_calls" 'web-health'
if grep -Eq 'plasma-(server|web)\.service' "$web_restart_calls"; then
  fail 'web-restart unexpectedly restarts Plasma Server or REST Gateway'
fi

grep -Fq 'web-restart|restart-web) restart_web_console' "$plasmactl_path" || fail 'web-restart command is not wired into plasmactl'

printf '[plasmactl-test] PASS\n'
