#!/usr/bin/env bash
# Deterministic source-only C library build; never installs or accesses Z2.
set -euo pipefail
if [[ $# -ne 2 || ( "$1" != host && "$1" != armv7 ) ]]; then
  echo "usage: $0 {host|armv7} ABSOLUTE_OUTPUT_SO" >&2
  exit 64
fi
mode="$1"
output="$2"
[[ "$output" = /* ]] || { echo "absolute output required" >&2; exit 64; }
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src="$repo/software/python/native/bluepill_wordport_bridge.c"
if [[ "$mode" == armv7 ]]; then
  compiler="${ARMV7_CC:-arm-linux-gnueabihf-gcc}"
  extra=(-march=armv7-a -marm -mfloat-abi=hard -mfpu=vfpv3)
else
  compiler="${HOST_CC:-gcc}"
  extra=()
fi
"$compiler" -std=c11 -O3 -fPIC -shared -Wall -Wextra -Werror \
  -fno-strict-aliasing -fstack-protector-strong \
  -Wl,-z,relro,-z,now "${extra[@]}" "$src" -o "$output"
sha256sum "$output"
