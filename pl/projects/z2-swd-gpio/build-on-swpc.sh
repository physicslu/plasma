#!/usr/bin/env bash
# RETIRED: source retained for historical tests only; no image builds.
printf '%s\n' 'RETIRED_Z2_SWD_GPIO: legacy project retired; use Z2 PS-local WordPort/PL SWD' >&2
exit 2
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

# Serialize reruns in this exact worktree. A previously interrupted SSH
# session must not leave two builds writing into the same Vivado project.
mkdir -p "$build"
if ! command -v flock >/dev/null 2>&1; then
  echo "flock is required for safe SWPC Vivado build serialization" >&2
  exit 2
fi
exec 9>"$build/.build.lock"
if ! flock -n 9; then
  echo "VIVADO_BUILD_BUSY: this worktree already has a build in progress" >&2
  exit 2
fi
echo "VIVADO_BUILD_LOCK_PASS"

# Machine-readable timing events (Unix epoch milliseconds). The foreground
# monitor combines these with Vivado Tcl stage events for exact step durations.
mkdir -p "$logdir"
stage_event() {
  printf 'STAGE_EVENT %s %s %s\n' "$1" "$2" "$(date +%s%3N)"
}
stage_event ENVIRONMENT START

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
stage_event ENVIRONMENT DONE

stage_event IDENTITY_PREPARE START

# Rebuild only this project's disposable output; never touch source or another
# project. Git-protected source dirty checks run BEFORE deleting generated data.
python3 "$script_dir/artifact.py" prepare --output "$generated" --version "$version"
stage_event IDENTITY_PREPARE DONE
stage_event STALE_PROJECT_CLEANUP START
if [[ "$project" != "$repo/pl/build/z2-swd-gpio/project" || -L "$project" ]]; then
  echo "Unsafe project directory (unexpected path/symlink); refusing cleanup" >&2
  exit 2
fi

# Avoid the ext4 'Directory not empty' race observed on SWPC while removing
# IP Integrator generated BD trees. Move old output out of the build path
# atomically first, then remove it best-effort. Never recycle the old project.
if [[ -e "$project" ]]; then
  [[ -d "$project" ]] || { echo "Unexpected non-directory Vivado project output" >&2; exit 2; }
  retired="$(mktemp -d "$build/.retired-project.XXXXXXXX")"
  if ! mv -T -- "$project" "$retired/project"; then
    rmdir -- "$retired" || true
    echo "Failed to quarantine stale Vivado project; refusing overwrite" >&2
    exit 2
  fi
  echo "VIVADO_STALE_PROJECT_QUARANTINED=$retired/project"
  if ! rm -rf -- "$retired"; then
    echo "WARNING: stale generated files could not be fully removed: $retired" >&2
    echo "WARNING: new build continues in a distinct fresh project path" >&2
  fi
fi
rm -rf -- "$build/artifacts"
stage_event STALE_PROJECT_CLEANUP DONE
mkdir -p "$logdir"
echo "=== VIVADO IMPLEMENTATION ==="
stage_event VIVADO START
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
stage_event VIVADO DONE

stage_event ARTIFACT_FINALIZE START

# Vivado 2026.1 prints "vivado v2026.1 (64-bit)" (lowercase),
# but some distributions use "Vivado". Parse both and reject malformed text.
vivado_version="$(vivado -version | sed -n '1s/^[[:space:]]*[Vv]ivado v\([0-9][0-9.]*\).*/\1/p')"
[[ -n "$vivado_version" ]] || { echo "Unable to read Vivado version" >&2; exit 2; }
python3 "$script_dir/artifact.py" finalize \
  --output "$generated" \
  --project "$project" \
  --identity-address-file "$generated/identity-axi-base.txt" \
  --vivado-version "$vivado_version"
stage_event ARTIFACT_FINALIZE DONE

stage_event SHA256_VERIFY START
echo "=== BITSTREAM / HWH DIGEST VALIDATION ==="
(cd "$build/artifacts" && sha256sum -c -- ./*.sha256)
stage_event SHA256_VERIFY DONE
echo "=== B/C SOURCE BUILD PASS (NO Z2 HIL) ==="
echo "Artifact dir : $build/artifacts"
echo "Reports      : $build/reports"
echo "Vivado log   : $logdir/vivado-console.log"
echo "=== REVIEW EVIDENCE: VIVADO LOG TAIL ==="
tail -n 35 "$logdir/vivado-console.log"
echo "=== REVIEW EVIDENCE: BITSTREAM MANIFEST ==="
cat "$build/artifacts/manifest.json"
echo "=== END REVIEW EVIDENCE ==="
