#!/usr/bin/env bash
# One-command SWPC build of Z2 EMIO + versioned PL identity. No Z2 access.
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$script_dir/../../.." && pwd)"
build="$repo/pl/build/z2-swd-gpio"
project="$build/project"
generated="$build/generated"
logdir="$build/logs"
version="${PLASMA_BITSTREAM_VERSION:-0.1.0}"
jobs="${PLASMA_VIVADO_JOBS:-4}"
export PLASMA_VIVADO_JOBS="$jobs"

# Prefer the SWPC-qualified Vivado 2026.1 installation when no explicit
# toolchain has been selected; keep the installed path configurable.
if [[ -z "${VIVADO_SETTINGS64:-}" && -f /storage/tools/xilinx/2026.1/Vivado/settings64.sh ]]; then
  VIVADO_SETTINGS64=/storage/tools/xilinx/2026.1/Vivado/settings64.sh
fi
if [[ -n "${VIVADO_SETTINGS64:-}" ]]; then
  [[ -f "$VIVADO_SETTINGS64" ]] || { echo "Missing Vivado settings file: $VIVADO_SETTINGS64" >&2; exit 2; }
  # shellcheck source=/dev/null
  source "$VIVADO_SETTINGS64"
fi
command -v vivado >/dev/null || {
  echo "Vivado not on PATH; source AMD Vivado settings64.sh or set VIVADO_SETTINGS64" >&2
  exit 2
}
export PLASMA_BOARD_REPO
PLASMA_BOARD_REPO="$(bash "$script_dir/prepare-board-repository.sh")"
echo "BOARD_REPO=$PLASMA_BOARD_REPO"
command -v python3 >/dev/null || { echo "python3 missing" >&2; exit 2; }
command -v git >/dev/null || { echo "git missing" >&2; exit 2; }

echo "=== PLASMA Z2 FPGA SOURCE CHECK ==="
git -C "$repo" rev-parse --short=12 HEAD
vivado -version | head -n 2

# Rebuild only this project's disposable output; never touch source or another
# project. Git-protected source dirty checks run BEFORE deleting generated data.
python3 "$script_dir/artifact.py" prepare --output "$generated" --version "$version"
if [[ "$project" != "$repo/pl/build/z2-swd-gpio/project" ]]; then
  echo "Unsafe project directory; refusing cleanup" >&2
  exit 2
fi
rm -rf -- "$project" "$build/artifacts"
mkdir -p "$logdir"
echo "=== VIVADO IMPLEMENTATION ==="
set +e
vivado -mode batch -nojournal \
  -log "$logdir/vivado-build.log" \
  -source "$script_dir/build_bitstream.tcl" \
  > "$logdir/vivado-console.log" 2>&1
result=$?
set -e
if ((result != 0)); then
  echo "VIVADO FAIL ($result) — $logdir/vivado-console.log" >&2
  tail -n 70 "$logdir/vivado-console.log" >&2
  exit "$result"
fi
if ! grep -Fq 'BITSTREAM_BUILD_PASS' "$logdir/vivado-console.log"; then
  echo "Vivado exited without success sentinel; refusing artifact" >&2
  tail -n 70 "$logdir/vivado-console.log" >&2
  exit 2
fi

vivado_version="$(vivado -version | sed -n '1s/.*Vivado v\([^[:space:]]*\).*/\1/p')"
[[ -n "$vivado_version" ]] || { echo "Unable to read Vivado version" >&2; exit 2; }
python3 "$script_dir/artifact.py" finalize \
  --output "$generated" \
  --project "$project" \
  --identity-address-file "$generated/identity-axi-base.txt" \
  --vivado-version "$vivado_version"

echo "=== BITSTREAM / HWH DIGEST VALIDATION ==="
(cd "$build/artifacts" && sha256sum -c -- ./*.sha256)
echo "=== B/C SOURCE BUILD PASS (NO Z2 HIL) ==="
echo "Artifact dir : $build/artifacts"
echo "Reports      : $build/reports"
echo "Vivado log   : $logdir/vivado-console.log"
echo "=== REVIEW EVIDENCE: VIVADO LOG TAIL ==="
tail -n 35 "$logdir/vivado-console.log"
echo "=== REVIEW EVIDENCE: BITSTREAM MANIFEST ==="
cat "$build/artifacts/manifest.json"
echo "=== END REVIEW EVIDENCE ==="
