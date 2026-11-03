#!/usr/bin/env bash
# Both cache HIT and MISS get fresh ARMv7 ELF, adapter and denial testing.
set -euo pipefail
test "$#" -eq 2
CACHE_DIR="$(realpath "$1")"
ARTIFACT_DIR="$(realpath -m "$2")"
mkdir -p "$ARTIFACT_DIR"
docker run --rm -i --platform linux/arm/v7 \
  --volume "$CACHE_DIR:/cache:ro" \
  --volume "$ARTIFACT_DIR:/artifacts" \
  arm32v7/ubuntu:22.04 bash -euo pipefail -s <<'ARMV7'
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends binutils libusb-1.0-0 libudev1
readelf -h /cache/openocd > /artifacts/elf-header.txt
grep -Eq 'Class:[[:space:]]+ELF32' /artifacts/elf-header.txt
grep -Eq 'Machine:[[:space:]]+ARM' /artifacts/elf-header.txt
/cache/openocd -s /cache/tcl -c 'adapter list' -c shutdown \
  > /artifacts/adapter-list.log 2>&1
grep -q plasma_swd /artifacts/adapter-list.log
/cache/openocd -s /cache/tcl -c 'adapter driver plasma_swd' \
  -c 'transport select swd' -c shutdown \
  > /artifacts/adapter-select.log 2>&1
set +e
/cache/openocd -s /cache/tcl -c 'adapter driver plasma_swd' \
  -c 'transport select swd' -c init -c shutdown \
  > /artifacts/unowned-init-denied.log 2>&1
unowned_exit=$?
set -e
test "$unowned_exit" -ne 0
grep -q PS_OWNER_SITE_NOT_SELECTED /artifacts/unowned-init-denied.log
set +e
/cache/openocd -s /cache/tcl -c 'adapter driver plasma_swd' \
  -c 'plasma_swd site 1' -c 'transport select swd' -c init \
  -c shutdown > /artifacts/unadmitted-site1-init-denied.log 2>&1
unadmitted_exit=$?
set -e
test "$unadmitted_exit" -ne 0
grep -Eq 'PS_OWNER_(SITE_LOCK_UNAVAILABLE|PL_IMAGE_NOT_LOADED|ROOT_REQUIRED)' \
  /artifacts/unadmitted-site1-init-denied.log
ldd /cache/openocd > /artifacts/linked-libraries.txt
if grep -q 'not found' /artifacts/linked-libraries.txt; then
  echo 'Missing ARMv7 shared library' >&2
  exit 1
fi
# Original Z2 library allowlist stays unchanged.
if grep -Ev '^[[:space:]]*(linux-vdso|/lib/ld-linux-armhf|(libc|libm|libpthread|libdl|librt|libgcc_s|libudev|libusb-1\.0)\.so)' \
    /artifacts/linked-libraries.txt; then
  echo 'ARMv7 binary links a library not present on Z2' >&2
  exit 1
fi
cp /cache/openocd /artifacts/openocd
cp -a /cache/tcl /artifacts/tcl
ARMV7
