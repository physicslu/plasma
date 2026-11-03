#!/usr/bin/env bash
# Cache only OpenOCD executable and upstream Tcl. Admission/evidence are per-HEAD.
set -euo pipefail
test "$#" -eq 1
: "$GITHUB_WORKSPACE"
CACHE_DIR="$(realpath -m "$1")"
mkdir -p "$CACHE_DIR"
# Non-hermetic apt and image tag: bump this explicit epoch on environment changes.
# The complete script is included in the Build Input Cache Key.
OPENOCD5088_TOOLCHAIN_EPOCH=1
docker run --rm -i --platform linux/arm/v7 \
  --volume "$GITHUB_WORKSPACE:/plasma:ro" \
  --volume "$CACHE_DIR:/cache" \
  arm32v7/ubuntu:22.04 bash -euo pipefail -s <<'ARMV7'
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  ca-certificates git autoconf automake libtool pkg-config make \
  gcc g++ python3 binutils libusb-1.0-0-dev
git init /tmp/openocd
git -C /tmp/openocd remote add origin https://github.com/openocd-org/openocd.git
git -C /tmp/openocd fetch --no-tags --depth 1 origin \
  5088db4c9154ca833c6d558381074b33672e127a
git -C /tmp/openocd checkout --detach FETCH_HEAD
test "$(git -C /tmp/openocd rev-parse HEAD)" = \
  5088db4c9154ca833c6d558381074b33672e127a
git -C /tmp/openocd submodule update --init --depth 1 jimtcl
python3 /plasma/scripts/ci/inject-plasma-openocd5088-native.py \
  --openocd /tmp/openocd --plasma /plasma
cd /tmp/openocd
./bootstrap
./configure --disable-werror --enable-internal-jimtcl \
  --disable-internal-libjaylink
make -j2
test -x src/openocd
cp src/openocd /cache/openocd
cp -a tcl /cache/tcl
ARMV7
