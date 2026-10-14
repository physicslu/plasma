#!/usr/bin/env bash
# Non-destructive environment diagnostic for the existing SWPC GitHub runner.
# No project checkout changes, synthesis, FPGA loading or DUT operations.
set -Eeuo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
log_dir="${PLASMA_FPGA_PREFLIGHT_LOG_DIR:-}"
if [[ -z "$log_dir" ]]; then
  log_dir="$(mktemp -d -t plasma-vivado-runner.XXXXXX)"
fi
mkdir -p "$log_dir"
echo "=== PLASMA SWPC VIVADO RUNNER PREFLIGHT ==="
echo "HOST=$(hostname)"
echo "USER=$(id -un)"
echo "UID=$(id -u)"
echo "RUNNER_NAME=${RUNNER_NAME:-NOT_IN_ACTIONS_RUNNER_JOB}"
echo "RUNNER_OS=${RUNNER_OS:-NOT_IN_ACTIONS_RUNNER_JOB}"
echo "LOG_DIR=$log_dir"

if [[ "$(id -u)" -eq 0 ]]; then
  echo "PREFLIGHT_FAIL: do not run Vivado as root; use the plasma-ci account" >&2
  exit 2
fi
if [[ -n "${PLASMA_EXPECT_SWPC_HOST:-}" && "$(hostname)" != "$PLASMA_EXPECT_SWPC_HOST" ]]; then
  echo "PREFLIGHT_FAIL: wrong host; expected $PLASMA_EXPECT_SWPC_HOST" >&2
  exit 2
fi
if [[ -n "${PLASMA_EXPECT_RUNNER_USER:-}" && "$(id -un)" != "$PLASMA_EXPECT_RUNNER_USER" ]]; then
  echo "PREFLIGHT_FAIL: wrong user; expected $PLASMA_EXPECT_RUNNER_USER" >&2
  exit 2
fi

if [[ -n "${VIVADO_SETTINGS64:-}" ]]; then
  if [[ ! -f "$VIVADO_SETTINGS64" ]]; then
    echo "PREFLIGHT_FAIL: VIVADO_SETTINGS64 does not exist: $VIVADO_SETTINGS64" >&2
    exit 2
  fi
  # shellcheck source=/dev/null
  source "$VIVADO_SETTINGS64"
fi

if ! command -v vivado >/dev/null 2>&1; then
  echo "PREFLIGHT_FAIL: vivado is not on PATH for this user/job" >&2
  echo "To use an installed Vivado, provide VIVADO_SETTINGS64=/actual/path/to/settings64.sh" >&2
  exit 2
fi
vivado_bin="$(command -v vivado)"
echo "VIVADO_BINARY=$vivado_bin"
echo "VIVADO_DIRECTORY=$(dirname "$vivado_bin")"

set +e
vivado -mode batch -nojournal -log "$log_dir/vivado.log" \
  -source "$script_dir/probe-vivado.tcl" \
  > "$log_dir/probe-console.log" 2>&1
result=$?
set -e
if ((result != 0)) || ! grep -Fq "PLASMA_VIVADO_PREFLIGHT_PASS" "$log_dir/probe-console.log"; then
  echo "PREFLIGHT_FAIL: Vivado returned $result or no success sentinel" >&2
  tail -n 80 "$log_dir/probe-console.log" >&2
  exit 2
fi
grep -E '^PLASMA_(VIVADO_VERSION|VIVADO_TARGET_PART|VIVADO_BOARD_PART|VIVADO_PREFLIGHT_PASS)' "$log_dir/probe-console.log"
echo "PREFLIGHT_PASS: Vivado executable, Zynq-7020 part and PYNQ-Z2 board preset recognized"
echo "LIMITATION: license checkout, synthesis, timing, bitstream, GPIO and Z2 HIL NOT TESTED"
echo "LOG=$log_dir/probe-console.log"
