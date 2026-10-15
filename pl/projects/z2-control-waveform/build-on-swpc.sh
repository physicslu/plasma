#!/usr/bin/env bash
# Host-only isolated Loopback baseline build; never loads FPGA or runs ps7_init.
set -Eeuo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$script_dir/../../.." && pwd)"
base="$repo/pl/build/z2-control-waveform"
mkdir -p "$base"
exec 9>"$base/.build.lock"
flock -n 9 || { echo "LOOPBACK_BUILD_BUSY" >&2; exit 2; }
# Preserve every prior build, including failed runs.
export PLASMA_LOOPBACK_BUILD
PLASMA_LOOPBACK_BUILD="$(mktemp -d "$base/run.XXXXXXXX")"
mkdir -p "$PLASMA_LOOPBACK_BUILD/logs"
echo "LOOPBACK_BUILD_DIR=$PLASMA_LOOPBACK_BUILD"
trap 'rc=$?; printf "EXIT_CODE=%s\n" "$rc" > "$PLASMA_LOOPBACK_BUILD/logs/build.status"' EXIT
# Mandatory host loopback gate before Vivado; pytest must include assertions.
"${PLASMA_TEST_PYTHON:-python3}" -m pytest -q "$repo/pl/verification/test_pspl02_swd00_rtl.py" > "$PLASMA_LOOPBACK_BUILD/logs/host-regression.log" 2>&1
python3 "$script_dir/artifact.py" prepare --build "$PLASMA_LOOPBACK_BUILD" --version "${PLASMA_BITSTREAM_VERSION:-0.1.0}"
settings="${VIVADO_SETTINGS64:-/storage/tools/xilinx/2026.1/Vivado/settings64.sh}"
source "$settings"
# A supplied pinned board cache is read-only; no changes to historical worktrees.
: "${PLASMA_BOARD_REPO:?Set PLASMA_BOARD_REPO to an existing pinned board repository}"
export PLASMA_BOARD_REPO
[[ "$(git -C "$PLASMA_BOARD_REPO" rev-parse HEAD)" == e02d6a3866b5465218f777168cdc51344ac94e07 ]]
[[ -z "$(git -C "$PLASMA_BOARD_REPO" status --porcelain --untracked-files=no)" ]]
export PLASMA_VIVADO_JOBS="${PLASMA_VIVADO_JOBS:-4}"
[[ "$PLASMA_VIVADO_JOBS" =~ ^([1-9]|[12][0-9]|3[0-2])$ ]]
vivado -mode batch -nojournal -log "$PLASMA_LOOPBACK_BUILD/logs/vivado-build.log" \
  -source "$script_dir/build_bitstream.tcl" > "$PLASMA_LOOPBACK_BUILD/logs/vivado-console.log" 2>&1
rg -q '^BITSTREAM_BUILD_PASS$' "$PLASMA_LOOPBACK_BUILD/logs/vivado-console.log"
vivado_version="$(vivado -version | sed -n '1s/^[[:space:]]*[Vv]ivado v\([0-9][0-9.]*\).*/\1/p')"
[[ -n "$vivado_version" ]]
python3 "$script_dir/artifact.py" finalize --build "$PLASMA_LOOPBACK_BUILD" --version "$vivado_version"
(cd "$PLASMA_LOOPBACK_BUILD/artifacts" && sha256sum -c -- ./*.sha256)
echo "LOOPBACK_BUILD_PASS_NO_HARDWARE_CLAIM"
