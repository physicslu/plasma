#!/usr/bin/env bash
# Interactive client for a detached, bounded SWPC Vivado build.
# "start" launches one supervisor and blocks while displaying progress;
# "attach" watches an existing supervisor, without starting another build.
# Ctrl-C/SSH disconnect detaches the client; the supervisor keeps running.
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$script_dir/../../.." && pwd)"
build="$repo/pl/build/z2-swd-gpio"
logdir="$build/logs"
status_file="$logdir/monitored-build.status"
monitor_log="$logdir/monitor.log"
pid_file="$logdir/monitored-build.pid"
mode="${1:-start}"

if [[ "$mode" != start && "$mode" != attach ]]; then
  echo "Usage: bash $0 [start | attach [SUPERVISOR_PID]]" >&2
  exit 2
fi
mkdir -p "$logdir"

if [[ "$mode" == start ]]; then
  command -v flock >/dev/null || { echo "flock not installed" >&2; exit 2; }
  command -v nohup >/dev/null || { echo "nohup not installed" >&2; exit 2; }
  command -v tail >/dev/null || { echo "tail not installed" >&2; exit 2; }

  # Serialize even a simultaneous launch from two SSH terminals.
  exec 7>"$build/.launch.lock"
  if ! flock -n 7; then
    echo "BUILD_LAUNCH_BUSY: another launch is underway" >&2
    exit 2
  fi

  if ! flock -n "$build/.monitor.lock" -c true || \
     ! flock -n "$build/.build.lock" -c true; then
    echo "BUILD_ALREADY_RUNNING: use 'attach' instead of starting a second build" >&2
    exit 2
  fi

  if [[ -n "$(git -C "$repo" status --porcelain --untracked-files=no)" ]]; then
    echo "Dirty tracked source files: refusing to start" >&2
    exit 2
  fi

  # The supervisor (not this SSH session) owns timeout and child cleanup.
  # Avoid inherited launcher lock in the detached process.
  flock -u 7
  exec 7>&-

  nohup env PLASMA_BUILD_TIMEOUT_MINUTES="${PLASMA_BUILD_TIMEOUT_MINUTES:-120}" \
    bash "$script_dir/run-monitored-on-swpc.sh" \
    > "$monitor_log" 2>&1 < /dev/null &
  pid=$!

  # The watched PID is bound to atomic status updates by the supervisor.
  printf '%s\n' "$pid" > "$pid_file"
  echo "BUILD_STARTED_SUPERVISOR_PID=$pid"
  echo "BUILD_CONTINUES_IF_SSH_DISCONNECTS"
else
  pid="${2:-}"
  if [[ -z "$pid" ]]; then
    [[ -s "$pid_file" ]] || { echo "Missing $pid_file; supply supervisor PID" >&2; exit 2; }
    pid="$(cat "$pid_file")"
  fi
fi

if [[ ! "$pid" =~ ^[1-9][0-9]*$ ]]; then
  echo "Invalid supervisor PID: $pid" >&2
  exit 2
fi
[[ -f "$monitor_log" ]] || { echo "Missing monitor log: $monitor_log" >&2; exit 2; }

echo "=== FOREGROUND BLOCKING MONITOR (PID=$pid) ==="
echo "The foreground client blocks until supervisor exits; Build stays detached."
echo "Press Ctrl-C to stop watching only."
tail -n 15 -f --pid="$pid" "$monitor_log" || true

echo "=== TERMINAL BUILD STATUS ==="
if [[ ! -f "$status_file" ]]; then
  echo "RESULT=UNKNOWN: no atomic status file (supervisor failed to initialize)" >&2
  exit 2
fi
cat "$status_file"

status="$(sed -n 's/^STATUS=//p' "$status_file" | tail -n 1)"
status_pid="$(sed -n 's/^SUPERVISOR_PID=//p' "$status_file" | tail -n 1)"
if [[ "$status_pid" != "$pid" ]]; then
  echo "RESULT=UNKNOWN: stale/unrelated status (expected PID=$pid, got $status_pid)" >&2
  exit 2
fi
case "$status" in
  PASS)    echo "RESULT=PASS"; exit 0 ;;
  FAIL)    echo "RESULT=FAIL"; exit 1 ;;
  TIMEOUT) echo "RESULT=TIMEOUT"; exit 124 ;;
  RUNNING) echo "RESULT=UNKNOWN: supervisor stopped without terminal status" >&2; exit 2 ;;
  *)       echo "RESULT=UNKNOWN: unexpected status $status" >&2; exit 2 ;;
esac
