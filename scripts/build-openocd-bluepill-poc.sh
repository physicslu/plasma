#!/usr/bin/env bash
# Development-only OpenOCD remote_bitbang/SWD toolchain proof.
# Does not modify release/openocd.json, install a runtime or touch hardware.
set -euo pipefail

if [[ $# -ne 1 || -z "$1" ]]; then
  echo "usage: $0 OUTPUT_DIRECTORY" >&2
  exit 2
fi
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
metadata="$repo_root/specs/bluepill-poc/openocd-remote-bitbang-v1.json"
read -r remote commit < <(python3 - "$metadata" <<'PY'
import json, re, sys
p = json.load(open(sys.argv[1], encoding="utf-8"))
assert p["schema"] == "plasma.bluepill.remote_bitbang_poc.v1"
assert p["status"] == "HOST_ONLY_CANDIDATE"
assert p["source_repository"] == "https://github.com/openocd-org/openocd.git"
assert re.fullmatch(r"[0-9a-f]{40}", p["source_commit"])
assert p["required_adapter"] == "remote_bitbang"
assert p["required_transport"] == "swd"
assert p["hardware_runtime_ready"] is False
print(p["source_repository"], p["source_commit"])
PY
)
out="$(mkdir -p "$1" && cd "$1" && pwd -P)"
source="$out/upstream"
prefix="$out/runtime"
if [[ -e "$source" || -e "$prefix" ]]; then
  echo "Refuse to overwrite an existing candidate build directory" >&2
  exit 2
fi
mkdir -p "$source"
git -C "$source" init -q
git -C "$source" remote add origin "$remote"
git -C "$source" fetch --depth 1 origin "$commit"
git -C "$source" checkout --detach FETCH_HEAD
test "$(git -C "$source" rev-parse HEAD)" = "$commit"
git -C "$source" submodule update --init --depth 1 jimtcl src/jtag/drivers/libjaylink
(
  cd "$source"
  ./bootstrap
  ./configure --prefix="$prefix" --disable-werror --disable-doxygen-html \
    --enable-internal-jimtcl --enable-dummy --enable-remote-bitbang --disable-jlink
  make -j2
  make install
)
"$prefix/bin/openocd" --version
"$prefix/bin/openocd" -c "adapter list" -c "shutdown" > "$out/adapter-list.txt" 2>&1
grep -Eq "^remote_bitbang[[:space:]]+\\{.*[[:space:]]swd[[:space:]]*\\}" "$out/adapter-list.txt"
"$prefix/bin/openocd" -c "adapter driver remote_bitbang" \
  -c "transport select swd" -c "shutdown" > "$out/swd-admission.txt" 2>&1
test -f "$out/swd-admission.txt"
printf '%s\n' "$commit" > "$out/openocd-source-sha.txt"
sha256sum "$prefix/bin/openocd" > "$out/openocd-binary.sha256"
echo "HOST_OPENOCD_REMOTE_BITBANG_SWD_ADMISSION_PASS (no ARMv7 / hardware claim)"
