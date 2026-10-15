#!/usr/bin/env bash
# HOST BUILD ONLY: creates a uniquely named Vivado run, never loads FPGA or
# executes ps7_init, and never modifies retained PSPL-02 baseline build files.
set -Eeuo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$script_dir/../../.." && pwd)"
base="$repo/pl/build/z2-swd03-axi"
mkdir -p "$base"
exec 9>"$base/.build.lock"
flock -n 9 || { echo "SWD03_BUILD_BUSY" >&2; exit 2; }

export PLASMA_SWD03_BUILD
PLASMA_SWD03_BUILD="$(mktemp -d "$base/run.XXXXXXXX")"
mkdir -p "$PLASMA_SWD03_BUILD/logs"
echo "SWD03_BUILD_DIR=$PLASMA_SWD03_BUILD"
trap 'rc=$?; printf "EXIT_CODE=%s\n" "$rc" > "$PLASMA_SWD03_BUILD/logs/build.status"' EXIT

# Separate, auditable host qualification gates: existing loopback and new SWD.
"${PLASMA_TEST_PYTHON:-python3}" -m pytest -q \
  "$repo/pl/verification/test_pspl02_swd00_rtl.py" \
  > "$PLASMA_SWD03_BUILD/logs/legacy-regression.log" 2>&1
"${PLASMA_TEST_PYTHON:-python3}" -m pytest -q \
  "$repo/pl/verification/test_swd_transaction_rtl.py" \
  "$repo/pl/verification/test_swd03_axi_rtl.py" \
  > "$PLASMA_SWD03_BUILD/logs/host-regression.log" 2>&1
"${PLASMA_TEST_PYTHON:-python3}" -m pytest -q \
  "$repo/pl/tests/test_z2_control_waveform_build.py" \
  "$repo/pl/tests/test_z2_swd03_axi_build.py" \
  > "$PLASMA_SWD03_BUILD/logs/artifact-regression.log" 2>&1

# Locks the exact tracked source revision; no dirty source may ship as commit.
python3 "$script_dir/artifact.py" prepare \
  --build "$PLASMA_SWD03_BUILD" \
  --version "${PLASMA_BITSTREAM_VERSION:-0.1.0}"

settings="${VIVADO_SETTINGS64:-/storage/tools/xilinx/2026.1/Vivado/settings64.sh}"
test -r "$settings"
source "$settings"
: "${PLASMA_BOARD_REPO:?Set PLASMA_BOARD_REPO to existing pinned board cache}"
export PLASMA_BOARD_REPO
[[ "$(git -C "$PLASMA_BOARD_REPO" rev-parse HEAD)" == e02d6a3866b5465218f777168cdc51344ac94e07 ]]
[[ -z "$(git -C "$PLASMA_BOARD_REPO" status --porcelain --untracked-files=no)" ]]
export PLASMA_VIVADO_JOBS="${PLASMA_VIVADO_JOBS:-4}"
[[ "$PLASMA_VIVADO_JOBS" =~ ^([1-9]|[12][0-9]|3[0-2])$ ]]

vivado -mode batch -nojournal -log "$PLASMA_SWD03_BUILD/logs/vivado-build.log" \
  -source "$script_dir/build_bitstream.tcl" \
  > "$PLASMA_SWD03_BUILD/logs/vivado-console.log" 2>&1
grep -qx 'SWD03_BITSTREAM_BUILD_PASS' "$PLASMA_SWD03_BUILD/logs/vivado-console.log"
vivado_version="$(vivado -version | sed -n '1s/^[[:space:]]*[Vv]ivado v\([0-9][0-9.]*\).*/\1/p')"
[[ -n "$vivado_version" ]]
python3 "$script_dir/artifact.py" finalize \
  --build "$PLASMA_SWD03_BUILD" --version "$vivado_version"
(cd "$PLASMA_SWD03_BUILD/artifacts" && sha256sum -c -- ./*.sha256)
echo "SWD03_HOST_ARTIFACT_PASS_NO_Z2_OR_TARGET_CLAIM"
