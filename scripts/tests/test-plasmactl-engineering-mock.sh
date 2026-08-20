#!/usr/bin/env bash
set -Eeuo pipefail

script_path="$(readlink -f "${BASH_SOURCE[0]}")"
repo="$(cd "$(dirname "$script_path")/../.." && pwd)"
plasmactl_path="${PLASMACTL_PATH:-$repo/scripts/plasmactl}"
temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT

fail() {
  printf '[engineering-mock-deploy-test] FAIL: %s\n' "$*" >&2
  exit 1
}

assert_file_line() {
  local file="$1" expected="$2"
  grep -Fxq "$expected" "$file" || fail "$file missing: $expected"
}

# Safe default: disabled, with mutable runtime state outside the Git worktree.
mapfile -t defaults < <(
  PLASMACTL_LIB_ONLY=1 \
  PLASMACTL_CONFIG="$temporary/no-default-config.env" \
  XDG_CONFIG_HOME="$temporary/default-config" \
  XDG_STATE_HOME="$temporary/default-state" \
  bash -c 'source "$1"; printf "%s\n%s\n" "$engineering_mock_enabled" "$engineering_mock_root"' _ "$plasmactl_path"
)
[[ "${defaults[0]}" == "0" ]] || fail "Engineering Mock must default disabled; got ${defaults[0]}"
[[ "${defaults[1]}" == "$temporary/default-state/plasma/engineering-mock" ]] || \
  fail "unexpected default Engineering Mock root: ${defaults[1]}"

# Enabling the provider changes only the Gateway command line. The provider is
# still part of plasma-web.service, not a second deployment service.
enabled_config="$temporary/enabled.env"
enabled_root="$temporary/runtime/engineering-mock"
printf '%s\n' \
  'PLASMA_CONFIG_VERSION=4' \
  'PLASMA_MANAGER_ENABLED=0' \
  "PLASMA_MANAGER_CONFIG=$temporary/manager.yaml" \
  'PLASMA_ENGINEERING_MOCK_ENABLED=1' \
  "PLASMA_ENGINEERING_MOCK_ROOT=$enabled_root" \
  >"$enabled_config"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$enabled_config" \
PLASMA_NPM=/usr/bin/true \
XDG_CONFIG_HOME="$temporary/enabled-config" \
XDG_STATE_HOME="$temporary/enabled-state" \
bash -c 'source "$1"; validate_unit_values; write_units' _ "$plasmactl_path"
enabled_unit="$temporary/enabled-config/systemd/user/plasma-web.service"
grep -Fq -- '--engineering-mock' "$enabled_unit" || fail 'enabled Gateway unit is missing --engineering-mock'
grep -Fq -- "--engineering-mock-root $enabled_root" "$enabled_unit" || \
  fail 'enabled Gateway unit is missing the configured Engineering Mock root'

# Disabled deployments must not expose a simulated fleet by accident.
disabled_config="$temporary/disabled.env"
printf '%s\n' \
  'PLASMA_CONFIG_VERSION=4' \
  'PLASMA_MANAGER_ENABLED=0' \
  "PLASMA_MANAGER_CONFIG=$temporary/manager-disabled.yaml" \
  'PLASMA_ENGINEERING_MOCK_ENABLED=0' \
  "PLASMA_ENGINEERING_MOCK_ROOT=$temporary/disabled-runtime" \
  >"$disabled_config"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$disabled_config" \
PLASMA_NPM=/usr/bin/true \
XDG_CONFIG_HOME="$temporary/disabled-config" \
XDG_STATE_HOME="$temporary/disabled-state" \
bash -c 'source "$1"; validate_unit_values; write_units' _ "$plasmactl_path"
disabled_unit="$temporary/disabled-config/systemd/user/plasma-web.service"
if grep -Fq -- '--engineering-mock' "$disabled_unit"; then
  fail 'disabled Gateway unit unexpectedly enables Engineering Mock Provider'
fi

# Invalid deployment values fail closed.
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$temporary/no-invalid-flag.env" \
PLASMA_ENGINEERING_MOCK_ENABLED=maybe \
PLASMA_ENGINEERING_MOCK_ROOT="$temporary/invalid-flag-root" \
XDG_CONFIG_HOME="$temporary/invalid-flag-config" \
XDG_STATE_HOME="$temporary/invalid-flag-state" \
bash -c 'source "$1"; validate_engineering_mock_settings' _ "$plasmactl_path" >/dev/null 2>&1 && \
  fail 'invalid Engineering Mock enablement was accepted'

PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$temporary/no-relative-root.env" \
PLASMA_ENGINEERING_MOCK_ENABLED=1 \
PLASMA_ENGINEERING_MOCK_ROOT=relative/mock-root \
XDG_CONFIG_HOME="$temporary/relative-root-config" \
XDG_STATE_HOME="$temporary/relative-root-state" \
bash -c 'source "$1"; validate_engineering_mock_settings' _ "$plasmactl_path" >/dev/null 2>&1 && \
  fail 'relative Engineering Mock root was accepted'

PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$temporary/no-worktree-root.env" \
PLASMA_ENGINEERING_MOCK_ENABLED=1 \
PLASMA_ENGINEERING_MOCK_ROOT="$repo/software/python/engineering-mock" \
XDG_CONFIG_HOME="$temporary/worktree-root-config" \
XDG_STATE_HOME="$temporary/worktree-root-state" \
bash -c 'source "$1"; validate_engineering_mock_settings' _ "$plasmactl_path" >/dev/null 2>&1 && \
  fail 'Engineering Mock root inside Git worktree was accepted'

# Health checking follows the deployment flag. This prevents a successful
# Gateway status probe from masking a failed Engineering Provider startup.
health_calls="$temporary/health-calls.txt"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$enabled_config" \
PLASMA_NPM=/usr/bin/true \
XDG_CONFIG_HOME="$temporary/health-enabled-config" \
XDG_STATE_HOME="$temporary/health-enabled-state" \
PLASMACTL_TEST_CALLS="$health_calls" \
bash -c '
  source "$1"
  require_command() { :; }
  wait_for_http() { printf "%s|%s\n" "$1" "$2" >>"$PLASMACTL_TEST_CALLS"; }
  engineering_mock_health_check
' _ "$plasmactl_path"
assert_file_line "$health_calls" 'http://127.0.0.1:18080/api/engineering/targets|Engineering Mock PPU Provider'

: >"$health_calls"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$disabled_config" \
PLASMA_NPM=/usr/bin/true \
XDG_CONFIG_HOME="$temporary/health-disabled-config" \
XDG_STATE_HOME="$temporary/health-disabled-state" \
PLASMACTL_TEST_CALLS="$health_calls" \
bash -c '
  source "$1"
  require_command() { :; }
  wait_for_http() { printf "unexpected\n" >>"$PLASMACTL_TEST_CALLS"; }
  engineering_mock_health_check
' _ "$plasmactl_path"
[[ ! -s "$health_calls" ]] || fail 'disabled Engineering Mock health check still probed the endpoint'

printf '[engineering-mock-deploy-test] PASS\n'