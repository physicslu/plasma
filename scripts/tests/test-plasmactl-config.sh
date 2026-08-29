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

assert_assignment_count() {
  local file="$1" key="$2" expected="$3" count
  count="$(grep -Ec "^${key}=" "$file" || true)"
  [[ "$count" == "$expected" ]] || fail "$file has $count assignments for $key; expected $expected"
}

resolve_default_public_api_url() {
  PLASMACTL_LIB_ONLY=1 \
  PLASMACTL_CONFIG="$temporary/no-config.env" \
  XDG_CONFIG_HOME="$temporary/xdg-default" \
  XDG_STATE_HOME="$temporary/state-default" \
  bash -c 'source "$1"; printf "%s\n" "$default_public_api_url"' _ "$plasmactl_path"
}

run_migration_case() {
  local name="$1" initial="$2" expected_url="$3" expected_version="$4"
  local config="$temporary/$name.env" output expected_manager_config expected_engineering_mock_root
  printf '%s\n' "$initial" >"$config"
  expected_manager_config="$temporary/xdg-$name/plasma/manager.yaml"
  expected_engineering_mock_root="$temporary/state-$name/plasma/engineering-mock"

  output="$({
    PLASMACTL_LIB_ONLY=1 \
    PLASMACTL_CONFIG="$config" \
    XDG_CONFIG_HOME="$temporary/xdg-$name" \
    XDG_STATE_HOME="$temporary/state-$name" \
    bash -c 'source "$1"; migrate_config; printf "%s\n" "$public_api_url"' _ "$plasmactl_path"
  })"

  [[ "${output##*$'\n'}" == "$expected_url" ]] || fail "$name resolved URL mismatch: $output"
  assert_file_line "$config" "PLASMA_CONFIG_VERSION=$expected_version"
  assert_file_line "$config" "PLASMA_PUBLIC_API_URL=$expected_url"
  assert_file_line "$config" 'PLASMA_MANAGER_ENABLED=0'
  assert_file_line "$config" "PLASMA_MANAGER_CONFIG=$expected_manager_config"
  assert_file_line "$config" 'PLASMA_MANAGER_PPU_ALIAS='
  assert_file_line "$config" 'PLASMA_ENGINEERING_MOCK_ENABLED=0'
  assert_file_line "$config" "PLASMA_ENGINEERING_MOCK_ROOT=$expected_engineering_mock_root"
}

default_public_api_url="$(resolve_default_public_api_url)"
[[ "$default_public_api_url" =~ ^https?:// ]] || fail "default public API URL is invalid: $default_public_api_url"

run_migration_case \
  legacy-tailscale \
  'PLASMA_PUBLIC_API_URL=https://swpc.tail820e64.ts.net:8443' \
  "$default_public_api_url" \
  '5'

run_migration_case \
  legacy-localhost \
  'PLASMA_PUBLIC_API_URL=http://127.0.0.1:8080' \
  "$default_public_api_url" \
  '5'

run_migration_case \
  custom-override \
  'PLASMA_PUBLIC_API_URL=https://lab-api.example.invalid' \
  'https://lab-api.example.invalid' \
  '5'

# A schema-v2 deployment already made an explicit API-base choice. Later
# migrations add Manager, Engineering Mock, and Manager BFF target settings but
# must not reinterpret the already-versioned API Base.
run_migration_case \
  already-v2 \
  $'PLASMA_CONFIG_VERSION=2\nPLASMA_PUBLIC_API_URL=https://swpc.tail820e64.ts.net:8443' \
  'https://swpc.tail820e64.ts.net:8443' \
  '5'

new_config="$temporary/new.env"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$new_config" \
XDG_CONFIG_HOME="$temporary/xdg-new" \
XDG_STATE_HOME="$temporary/state-new" \
bash -c 'source "$1"; write_config' _ "$plasmactl_path" >/dev/null
assert_file_line "$new_config" 'PLASMA_CONFIG_VERSION=5'
assert_file_line "$new_config" "PLASMA_PUBLIC_API_URL=$default_public_api_url"
assert_file_line "$new_config" 'PLASMA_MANAGER_ENABLED=0'
assert_file_line "$new_config" "PLASMA_MANAGER_CONFIG=$temporary/xdg-new/plasma/manager.yaml"
assert_file_line "$new_config" 'PLASMA_MANAGER_PPU_ALIAS='
assert_file_line "$new_config" 'PLASMA_ENGINEERING_MOCK_ENABLED=0'
assert_file_line "$new_config" "PLASMA_ENGINEERING_MOCK_ROOT=$temporary/state-new/plasma/engineering-mock"

# A schema-version marker is not sufficient evidence that every field added by
# that schema is present. Reconcile an already-v4 incomplete file into schema v5
# using safe defaults, then prove the repair is idempotent.
incomplete_v4="$temporary/incomplete-v4.env"
printf '%s\n' \
  'PLASMA_CONFIG_VERSION=4' \
  'PLASMA_PUBLIC_API_URL=https://operator.example.invalid' \
  >"$incomplete_v4"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$incomplete_v4" \
XDG_CONFIG_HOME="$temporary/xdg-incomplete-v4" \
XDG_STATE_HOME="$temporary/state-incomplete-v4" \
bash -c 'source "$1"; write_config' _ "$plasmactl_path" >/dev/null
assert_file_line "$incomplete_v4" 'PLASMA_CONFIG_VERSION=5'
assert_file_line "$incomplete_v4" 'PLASMA_PUBLIC_API_URL=https://operator.example.invalid'
assert_file_line "$incomplete_v4" 'PLASMA_MANAGER_ENABLED=0'
assert_file_line "$incomplete_v4" "PLASMA_MANAGER_CONFIG=$temporary/xdg-incomplete-v4/plasma/manager.yaml"
assert_file_line "$incomplete_v4" 'PLASMA_MANAGER_PPU_ALIAS='
assert_file_line "$incomplete_v4" 'PLASMA_ENGINEERING_MOCK_ENABLED=0'
assert_file_line "$incomplete_v4" "PLASMA_ENGINEERING_MOCK_ROOT=$temporary/state-incomplete-v4/plasma/engineering-mock"
assert_assignment_count "$incomplete_v4" PLASMA_MANAGER_ENABLED 1
assert_assignment_count "$incomplete_v4" PLASMA_MANAGER_CONFIG 1
assert_assignment_count "$incomplete_v4" PLASMA_MANAGER_PPU_ALIAS 1
assert_assignment_count "$incomplete_v4" PLASMA_ENGINEERING_MOCK_ENABLED 1
assert_assignment_count "$incomplete_v4" PLASMA_ENGINEERING_MOCK_ROOT 1
incomplete_hash_before="$(sha256sum "$incomplete_v4" | awk '{print $1}')"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$incomplete_v4" \
XDG_CONFIG_HOME="$temporary/xdg-incomplete-v4" \
XDG_STATE_HOME="$temporary/state-incomplete-v4" \
bash -c 'source "$1"; write_config' _ "$plasmactl_path" >/dev/null
incomplete_hash_after="$(sha256sum "$incomplete_v4" | awk '{print $1}')"
[[ "$incomplete_hash_before" == "$incomplete_hash_after" ]] || \
  fail 'schema-v5 completeness repair is not idempotent'

# Partial old-schema files preserve operator-owned values and synthesize only
# missing assignments. Never rewrite explicit Manager settings.
partial_enabled="$temporary/partial-enabled-v4.env"
printf '%s\n' \
  'PLASMA_CONFIG_VERSION=4' \
  'PLASMA_MANAGER_ENABLED=1' \
  >"$partial_enabled"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$partial_enabled" \
XDG_CONFIG_HOME="$temporary/xdg-partial-enabled" \
XDG_STATE_HOME="$temporary/state-partial-enabled" \
bash -c 'source "$1"; migrate_config' _ "$plasmactl_path" >/dev/null
assert_file_line "$partial_enabled" 'PLASMA_CONFIG_VERSION=5'
assert_file_line "$partial_enabled" 'PLASMA_MANAGER_ENABLED=1'
assert_file_line "$partial_enabled" "PLASMA_MANAGER_CONFIG=$temporary/xdg-partial-enabled/plasma/manager.yaml"
assert_file_line "$partial_enabled" 'PLASMA_MANAGER_PPU_ALIAS='
assert_assignment_count "$partial_enabled" PLASMA_MANAGER_ENABLED 1
assert_assignment_count "$partial_enabled" PLASMA_MANAGER_CONFIG 1
assert_assignment_count "$partial_enabled" PLASMA_MANAGER_PPU_ALIAS 1

partial_path="$temporary/partial-path-v4.env"
custom_manager_path="$temporary/operator/manager.yaml"
printf '%s\n' \
  'PLASMA_CONFIG_VERSION=4' \
  "PLASMA_MANAGER_CONFIG=$custom_manager_path" \
  >"$partial_path"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$partial_path" \
XDG_CONFIG_HOME="$temporary/xdg-partial-path" \
XDG_STATE_HOME="$temporary/state-partial-path" \
bash -c 'source "$1"; migrate_config' _ "$plasmactl_path" >/dev/null
assert_file_line "$partial_path" 'PLASMA_CONFIG_VERSION=5'
assert_file_line "$partial_path" 'PLASMA_MANAGER_ENABLED=0'
assert_file_line "$partial_path" "PLASMA_MANAGER_CONFIG=$custom_manager_path"
assert_file_line "$partial_path" 'PLASMA_MANAGER_PPU_ALIAS='
assert_assignment_count "$partial_path" PLASMA_MANAGER_ENABLED 1
assert_assignment_count "$partial_path" PLASMA_MANAGER_CONFIG 1
assert_assignment_count "$partial_path" PLASMA_MANAGER_PPU_ALIAS 1

# An explicit alias already present in a v4 deployment is operator-owned input
# and must survive the schema-v5 migration unchanged.
explicit_alias="$temporary/explicit-alias-v4.env"
printf '%s\n' \
  'PLASMA_CONFIG_VERSION=4' \
  'PLASMA_MANAGER_ENABLED=1' \
  'PLASMA_MANAGER_PPU_ALIAS=ppu-a' \
  >"$explicit_alias"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$explicit_alias" \
XDG_CONFIG_HOME="$temporary/xdg-explicit-alias" \
XDG_STATE_HOME="$temporary/state-explicit-alias" \
bash -c 'source "$1"; migrate_config' _ "$plasmactl_path" >/dev/null
assert_file_line "$explicit_alias" 'PLASMA_CONFIG_VERSION=5'
assert_file_line "$explicit_alias" 'PLASMA_MANAGER_PPU_ALIAS=ppu-a'
assert_assignment_count "$explicit_alias" PLASMA_MANAGER_PPU_ALIAS 1

# An older plasmactl must not mutate a future schema it does not understand.
future_config="$temporary/future-schema.env"
printf '%s\n' 'PLASMA_CONFIG_VERSION=6' >"$future_config"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$future_config" \
XDG_CONFIG_HOME="$temporary/xdg-future" \
XDG_STATE_HOME="$temporary/state-future" \
bash -c 'source "$1"; migrate_config' _ "$plasmactl_path" >/dev/null 2>&1 && \
  fail 'future deployment schema was accepted and could be mutated by an older plasmactl'

unit_config="$temporary/unit-migration.env"
printf '%s\n' 'PLASMA_PUBLIC_API_URL=https://swpc.tail820e64.ts.net:8443' >"$unit_config"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$unit_config" \
XDG_CONFIG_HOME="$temporary/xdg-unit" \
XDG_STATE_HOME="$temporary/state-unit" \
bash -c 'source "$1"; migrate_config; write_units' _ "$plasmactl_path" >/dev/null
assert_file_line \
  "$temporary/xdg-unit/systemd/user/plasma-vite.service" \
  "Environment=NEXT_PUBLIC_PLASMA_API_URL=$default_public_api_url"
assert_file_line \
  "$temporary/xdg-unit/systemd/user/plasma-manager.service" \
  "ExecStart=$repo/software/python/.venv/bin/python -m plasma_manager.server --config $temporary/xdg-unit/plasma/manager.yaml"
if grep -Fq 'PLASMA_MANAGER_API_URL=' "$temporary/xdg-unit/systemd/user/plasma-vite.service" || \
   grep -Fq 'PLASMA_MANAGER_PPU_ALIAS=' "$temporary/xdg-unit/systemd/user/plasma-vite.service"; then
  fail 'Manager BFF environment leaked into Vite while Manager is disabled'
fi
if grep -Fq 'plasma-web.service' "$temporary/xdg-unit/systemd/user/plasma-manager.service"; then
  fail 'Manager systemd unit must not depend on the local PPU Gateway'
fi
if grep -Fq -- '--engineering-mock' "$temporary/xdg-unit/systemd/user/plasma-web.service"; then
  fail 'Engineering Mock Provider was enabled by default during migration'
fi

# The endpoint is configuration, not a fixed product constant. A valid explicit
# site value must survive schema handling and propagate unchanged into the
# generated runtime unit.
custom_runtime_url='https://programmer.customer.example.invalid'
custom_unit_config="$temporary/unit-custom.env"
printf '%s\n' \
  'PLASMA_CONFIG_VERSION=4' \
  "PLASMA_PUBLIC_API_URL=$custom_runtime_url" \
  'PLASMA_MANAGER_ENABLED=0' \
  "PLASMA_MANAGER_CONFIG=$temporary/xdg-custom-unit/plasma/manager.yaml" \
  >"$custom_unit_config"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$custom_unit_config" \
XDG_CONFIG_HOME="$temporary/xdg-custom-unit" \
XDG_STATE_HOME="$temporary/state-custom-unit" \
bash -c 'source "$1"; migrate_config; write_units' _ "$plasmactl_path" >/dev/null
assert_file_line "$custom_unit_config" 'PLASMA_CONFIG_VERSION=5'
assert_file_line "$custom_unit_config" "PLASMA_PUBLIC_API_URL=$custom_runtime_url"
assert_file_line "$custom_unit_config" 'PLASMA_MANAGER_PPU_ALIAS='
assert_file_line \
  "$temporary/xdg-custom-unit/systemd/user/plasma-vite.service" \
  "Environment=NEXT_PUBLIC_PLASMA_API_URL=$custom_runtime_url"

# Manager remains opt-in. This pre-install shell test checks deployment wiring
# without parsing YAML; manager_bff_url is stubbed here. Python tests cover the
# actual Manager registry and loopback-bind validation after dependencies exist.
manager_yaml="$temporary/manager-enabled.yaml"
cat >"$manager_yaml" <<'YAML'
manager:
  host: 127.0.0.1
  port: 19180
  request_timeout_s: 2.0
ppus:
  - endpoint: http://127.0.0.1:18080
    alias: ppu-a
YAML

PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$temporary/no-manager.env" \
XDG_CONFIG_HOME="$temporary/xdg-manager-disabled" \
XDG_STATE_HOME="$temporary/state-manager-disabled" \
bash -c '
  set -Eeuo pipefail
  source "$1"
  [[ " ${services[*]} " != *" plasma-manager.service "* ]]
' _ "$plasmactl_path" || fail 'Manager unexpectedly enters service set while disabled'

manager_enabled_config="$temporary/manager-enabled.env"
printf '%s\n' \
  'PLASMA_CONFIG_VERSION=5' \
  'PLASMA_MANAGER_ENABLED=1' \
  "PLASMA_MANAGER_CONFIG=$manager_yaml" \
  'PLASMA_MANAGER_PPU_ALIAS=ppu-a' \
  >"$manager_enabled_config"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$manager_enabled_config" \
PLASMA_PYTHON="$(command -v python3)" \
XDG_CONFIG_HOME="$temporary/xdg-manager-enabled" \
XDG_STATE_HOME="$temporary/state-manager-enabled" \
bash -c '
  set -Eeuo pipefail
  source "$1"
  [[ " ${services[*]} " == *" plasma-manager.service "* ]]
  manager_bff_url() { printf "http://127.0.0.1:19180\n"; }
  validate_unit_values
  write_units
' _ "$plasmactl_path" || fail 'Manager opt-in deployment wiring contract failed'
assert_file_line \
  "$temporary/xdg-manager-enabled/systemd/user/plasma-manager.service" \
  "ExecStart=$(command -v python3) -m plasma_manager.server --config $manager_yaml"
assert_file_line \
  "$temporary/xdg-manager-enabled/systemd/user/plasma-vite.service" \
  'Environment=PLASMA_MANAGER_API_URL=http://127.0.0.1:19180'
assert_file_line \
  "$temporary/xdg-manager-enabled/systemd/user/plasma-vite.service" \
  'Environment=PLASMA_MANAGER_PPU_ALIAS=ppu-a'
assert_file_line \
  "$temporary/xdg-manager-enabled/systemd/user/plasma-vite.service" \
  'After=network-online.target plasma-web.service plasma-manager.service'
assert_file_line \
  "$temporary/xdg-manager-enabled/systemd/user/plasma-vite.service" \
  'Wants=network-online.target plasma-web.service plasma-manager.service'

# Missing or unsafe BFF aliases fail closed when Manager is enabled.
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$temporary/no-manager-alias.env" \
PLASMA_MANAGER_ENABLED=1 \
XDG_CONFIG_HOME="$temporary/xdg-manager-no-alias" \
XDG_STATE_HOME="$temporary/state-manager-no-alias" \
bash -c 'source "$1"; validate_manager_settings' _ "$plasmactl_path" >/dev/null 2>&1 && \
  fail 'Manager enabled without PLASMA_MANAGER_PPU_ALIAS was accepted'

PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$temporary/no-invalid-alias.env" \
PLASMA_MANAGER_ENABLED=1 \
PLASMA_MANAGER_PPU_ALIAS='bad/alias' \
XDG_CONFIG_HOME="$temporary/xdg-manager-bad-alias" \
XDG_STATE_HOME="$temporary/state-manager-bad-alias" \
bash -c 'source "$1"; validate_manager_settings' _ "$plasmactl_path" >/dev/null 2>&1 && \
  fail 'unsafe PLASMA_MANAGER_PPU_ALIAS value was accepted'

# Invalid opt-in values fail closed rather than silently changing runtime scope.
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$temporary/no-invalid-manager.env" \
PLASMA_MANAGER_ENABLED=maybe \
XDG_CONFIG_HOME="$temporary/xdg-manager-invalid" \
XDG_STATE_HOME="$temporary/state-manager-invalid" \
bash -c 'source "$1"; validate_manager_settings' _ "$plasmactl_path" >/dev/null 2>&1 && \
  fail 'invalid PLASMA_MANAGER_ENABLED value was accepted'

grep -Fq 'PLASMACTL_DEPLOY_REEXEC=1 exec "$script_path" deploy' "$plasmactl_path" || fail 'deploy does not re-exec updated plasmactl'
grep -Fq 'reconcile_service_units' "$plasmactl_path" || fail 'service-unit reconciliation is missing'
grep -Fq 'ensure_config_completeness' "$plasmactl_path" || fail 'deployment config completeness reconciliation is missing'
grep -Fq 'manager_health_check' "$plasmactl_path" || fail 'Manager health check integration is missing'
grep -Fq 'engineering_mock_health_check' "$plasmactl_path" || fail 'Engineering Mock Provider health check integration is missing'
grep -Fq 'systemctl --user is-active --quiet plasma-manager.service' "$plasmactl_path" || fail 'Manager health check does not verify systemd service ownership'
grep -Fq 'manager) units=(-u plasma-manager.service)' "$plasmactl_path" || fail 'Manager log target is missing'
grep -Fq 'PLASMA_MANAGER_PPU_ALIAS' "$plasmactl_path" || fail 'Manager BFF target alias deployment wiring is missing'
grep -Fq 'PLASMA_MANAGER_API_URL' "$plasmactl_path" || fail 'Manager BFF API URL deployment wiring is missing'

# Web deployment hygiene: source changes make a long-running Vite runtime stale,
# but package metadata alone must not cause npm ci under the live dev server.
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$temporary/no-hygiene-config.env" \
PLASMA_PYTHON="$(command -v python3)" \
XDG_CONFIG_HOME="$temporary/xdg-hygiene" \
XDG_STATE_HOME="$temporary/state-hygiene" \
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
# execute the Web health check. It must not bounce the programming server, REST
# Gateway, optional Manager, or Engineering Mock provider independently.
web_restart_calls="$temporary/web-restart-calls.txt"
PLASMACTL_LIB_ONLY=1 \
PLASMACTL_CONFIG="$temporary/no-restart-config.env" \
PLASMA_PYTHON="$(command -v python3)" \
XDG_CONFIG_HOME="$temporary/xdg-restart" \
XDG_STATE_HOME="$temporary/state-restart" \
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
if grep -Eq 'plasma-(server|web|manager)\.service' "$web_restart_calls"; then
  fail 'web-restart unexpectedly restarts Plasma Server, REST Gateway, or Manager'
fi

grep -Fq 'web-restart|restart-web) restart_web_console' "$plasmactl_path" || fail 'web-restart command is not wired into plasmactl'

printf '[plasmactl-test] PASS\n'