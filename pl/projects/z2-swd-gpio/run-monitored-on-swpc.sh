#!/usr/bin/env bash
# Detached SWPC Vivado build supervisor. Fail/timeout stops this build only.
# No FPGA load, no IC access, no Git writes or PR merge.
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$script_dir/../../.." && pwd)"
build="$repo/pl/build/z2-swd-gpio"
logdir="$build/logs"
driver="$logdir/driver.log"
vivado_log="$logdir/vivado-console.log"
status_file="$logdir/monitored-build.status"
minutes="${PLASMA_BUILD_TIMEOUT_MINUTES:-120}"

if [[ ! "$minutes" =~ ^[1-9][0-9]*$ ]] || ((minutes > 360)); then
  echo "Invalid timeout: PLASMA_BUILD_TIMEOUT_MINUTES must be 1..360" >&2
  exit 2
fi
command -v timeout >/dev/null || { echo "GNU timeout is required" >&2; exit 2; }
command -v flock >/dev/null || { echo "flock is required" >&2; exit 2; }
mkdir -p "$logdir"

# Protect the supervisor as well as the build; build-on-swpc.sh separately
# holds .build.lock so competing direct builds fail closed.
exec 8>"$build/.monitor.lock"
if ! flock -n 8; then
  echo "MONITOR_BUSY: another supervisor is already running" >&2
  exit 2
fi
if flock -n "$build/.build.lock" -c true; then
  : # no build in progress
else
  echo "VIVADO_BUILD_BUSY: refusing to supervise a second build" >&2
  exit 2
fi

commit="$(git -C "$repo" rev-parse HEAD)"
if [[ -n "$(git -C "$repo" status --porcelain --untracked-files=no)" ]]; then
  echo "Source checkout has modified tracked files; refusing monitored build" >&2
  exit 2
fi

write_status() {
  local state="$1" code="$2" temp="$status_file.tmp.$$"
  printf 'STATUS=%s\nEXIT_CODE=%s\nSOURCE_SHA=%s\nSUPERVISOR_PID=%s\nUPDATED_AT=%s\n' \
    "$state" "$code" "$commit" "$" "$(date -Is)" > "$temp"
  mv -f -- "$temp" "$status_file"
}

write_status RUNNING '-'
echo "MONITOR_STARTED=$(date -Is)"
echo "SOURCE_SHA=$commit"
echo "TIMEOUT_MINUTES=$minutes"
echo "DRIVER_LOG=$driver"

# timeout manages a child process group, including Vivado's child runs.
# A deadline sends TERM; if necessary KILL follows 60 seconds later.
# The enclosing nohup job itself has no Vivado session dependency.
set +e
timeout --signal=TERM --kill-after=60s "${minutes}m" \
  bash "$script_dir/build-on-swpc.sh" > "$driver" 2>&1 &
build_pid=$!
set -e

while kill -0 "$build_pid" 2>/dev/null; do
  echo "MONITOR_HEARTBEAT=$(date -Is) RUNNING"
  if [[ -f "$vivado_log" ]]; then
    grep -E '^(BLOCK_DESIGN_VALIDATED|PROJECT_CREATED|IMPLEMENTED_TIMING_PASS|BITSTREAM_BUILD_PASS|ERROR:)' \
      "$vivado_log" | tail -n 3 || true
  fi
  sleep 60
done

code=0
wait "$build_pid" || code=$?
if ((code == 0)) && \
   grep -Fq '=== END REVIEW EVIDENCE ===' "$driver" && \
   [[ -s "$build/artifacts/manifest.json" ]]; then
  write_status PASS 0
  echo "MONITOR_RESULT=PASS"
  echo "ARTIFACTS=$build/artifacts"
  exit 0
fi
if ((code == 124)); then
  write_status TIMEOUT "$code"
  echo "MONITOR_RESULT=TIMEOUT BUILD_TERMINATED_AT_LIMIT"
  exit 124
fi
if ((code == 0)); then
  code=2 # driver exited zero without validated manifest + success sentinel
fi
write_status FAIL "$code"
echo "MONITOR_RESULT=FAIL EXIT_CODE=$code"
tail -n 45 "$driver" || true
exit "$code"
