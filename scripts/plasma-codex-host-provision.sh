#!/usr/bin/env bash
# PLASMA Issue #981 — reviewed host-only bootstrap, not runner enrollment.
# --check: read-only inventory; --apply: one-time SWPC administrator operation.
set -Eeuo pipefail
umask 077

usage() {
  printf '%s\n' "Usage: bash scripts/plasma-codex-host-provision.sh --check|--apply"
  exit "${1:-0}"
}
(( $# == 1 )) || usage
case "$1" in --check|--apply) mode="$1";; -h|--help) usage 0;; *) usage 2;; esac

worker=plasma-codex
owner=gordon
monitor_group=plasma-monitor
home=/home/plasma-codex
runner_dir="$home/actions-runner"
monitor_dir=/run/plasma-codex
tmpfiles=/etc/tmpfiles.d/plasma-codex.conf
tmpfiles_rule="d /run/plasma-codex 2770 plasma-codex plasma-monitor - -"

fail() { printf 'BLOCKED: %s\n' "$*" >&2; exit 1; }
has_user() { getent passwd "$1" >/dev/null; }
has_group() { getent group "$1" >/dev/null; }
group_member() { id -nG "$1" 2>/dev/null | tr ' ' '\n' | grep -qx "$2"; }

report() {
  for user in "$owner" "$worker"; do
    if has_user "$user"; then printf 'user_%s=PRESENT\n' "$user"; else printf 'user_%s=ABSENT\n' "$user"; fi
  done
  if has_group "$monitor_group"; then printf 'monitor_group=PRESENT\n'; else printf 'monitor_group=ABSENT\n'; fi
  if [[ -d "$monitor_dir" && ! -L "$monitor_dir" ]]; then
    printf 'monitor_dir=EXISTS owner=%s group=%s mode=%s\n' \
      "$(stat -c '%U' "$monitor_dir")" "$(stat -c '%G' "$monitor_dir")" \
      "$(stat -c '%a' "$monitor_dir")"
  else
    printf 'monitor_dir=ABSENT\n'
  fi
  if [[ -f "$tmpfiles" && ! -L "$tmpfiles" ]]; then
    if [[ "$(cat "$tmpfiles")" == "$tmpfiles_rule" ]]; then
      printf 'tmpfiles_rule=EXPECTED\n'
    else
      printf 'tmpfiles_rule=CONFLICT\n'
    fi
  else
    printf 'tmpfiles_rule=ABSENT\n'
  fi
  if [[ -d "$runner_dir" && ! -L "$runner_dir" ]]; then
    printf 'runner_dir=EXISTS\n'
  else
    printf 'runner_dir=ABSENT\n'
  fi
  printf '%s\n' 'runner_registration=NOT_CHECKED codex_auth=NOT_CHECKED hardware=NOT_TOUCHED'
}

[[ "$(hostname)" == SWPC ]] || fail "Host must be SWPC; nothing changed"
if [[ "$mode" == --check ]]; then
  report
  exit 0
fi

# The GitHub Actions runner, including the existing plasma-ci identity, must
# never become an implicit administrator simply because an Issue was approved.
(( EUID == 0 )) || fail "--apply requires an existing owner-authorized SWPC administrator channel"
[[ -z "${GITHUB_ACTIONS:-}" ]] || fail "--apply cannot run in GitHub Actions"
for cmd in useradd groupadd usermod getent id stat install systemd-tmpfiles; do
  command -v "$cmd" >/dev/null || fail "Missing required administration command: $cmd"
done
has_user "$owner" || fail "Trusted operator account $owner does not exist"

# Stop on unexpected reused system identities or pre-existing custom settings.
if has_user "$worker"; then
  line="$(getent passwd "$worker")"
  IFS=: read -r _ _ uid _ _ actual_home actual_shell <<< "$line"
  [[ "$uid" =~ ^[0-9]+$ && "$uid" != 0 ]] || fail "Worker account has unsafe UID"
  [[ "$actual_home" == "$home" && "$actual_shell" == /bin/bash ]] || fail "Worker identity conflicts with expected home/shell"
fi
if [[ -e "$tmpfiles" || -L "$tmpfiles" ]]; then
  [[ -f "$tmpfiles" && ! -L "$tmpfiles" ]] || fail "Unexpected tmpfiles path"
  [[ "$(cat "$tmpfiles")" == "$tmpfiles_rule" ]] || fail "Conflicting tmpfiles configuration; refusing overwrite"
fi
if [[ -e "$home" && -L "$home" ]] || [[ -e "$runner_dir" && -L "$runner_dir" ]]; then
  fail "Unsafe symbolic link in dedicated worker paths"
fi
if [[ -e "$monitor_dir" && ( ! -d "$monitor_dir" || -L "$monitor_dir" ) ]]; then
  fail "Unexpected monitor socket directory"
fi

if ! has_group "$monitor_group"; then
  groupadd --system "$monitor_group"
fi
if ! has_user "$worker"; then
  useradd --system --create-home --user-group --home-dir "$home" --shell /bin/bash "$worker"
fi

# Do not add worker or plasma-ci to sudo/docker or any hardware access group.
for forbidden in sudo docker adm dialout gpio i2c video plasma-hil; do
  if group_member "$worker" "$forbidden"; then
    fail "Worker already has prohibited membership: $forbidden"
  fi
done
for user in "$worker" "$owner"; do
  if ! group_member "$user" "$monitor_group"; then
    usermod -a -G "$monitor_group" "$user"
  fi
done

[[ "$(stat -c '%U' "$home")" == "$worker" ]] || fail "Unexpected worker HOME owner"
chmod 0700 "$home"
if [[ -e "$runner_dir" ]]; then
  [[ -d "$runner_dir" && ! -L "$runner_dir" ]] || fail "Unsafe runner directory"
  [[ "$(stat -c '%U' "$runner_dir")" == "$worker" ]] || fail "Existing runner dir is not owned by worker"
  chmod 0700 "$runner_dir"
else
  install -d -m 0700 -o "$worker" -g "$worker" "$runner_dir"
fi

if [[ ! -e "$tmpfiles" ]]; then
  printf '%s\n' "$tmpfiles_rule" > "$tmpfiles"
  chmod 0644 "$tmpfiles"
fi
systemd-tmpfiles --create "$tmpfiles"
[[ -d "$monitor_dir" && ! -L "$monitor_dir" ]] || fail "Monitor directory not created"
[[ "$(stat -c '%U:%G:%a' "$monitor_dir")" == "$worker:$monitor_group:2770" ]] || fail "Unexpected monitor directory owner/mode"

printf '%s\n' 'HOST_PREPARED: dedicated account/group/monitor directory only'
printf '%s\n' 'NOT DONE: GitHub runner registration, Codex CLI/auth, service startup, hardware qualification'
printf '%s\n' 'Operator must re-login over SSH to activate new group membership.'
report
