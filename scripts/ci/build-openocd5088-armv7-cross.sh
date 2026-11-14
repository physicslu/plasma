#!/usr/bin/env bash
# Experimental GitHub-hosted x86_64 -> ARMv7 hard-float cold build only.
# Do not replace the source-locked QEMU candidate builder or release artifacts.
set -euo pipefail
test "$#" -eq 1
: "${GITHUB_WORKSPACE:?GitHub-hosted checkout required}"
OUTPUT_DIR="$(realpath -m "$1")"
mkdir -p "$OUTPUT_DIR"

docker run --rm -i --platform linux/amd64 \
  --volume "$GITHUB_WORKSPACE:/plasma:ro" \
  --volume "$OUTPUT_DIR:/cross-output" \
  ubuntu:22.04 bash -euo pipefail -s <<'CROSS'
export DEBIAN_FRONTEND=noninteractive
# Ubuntu's amd64 archive does not publish armhf indexes; armhf lives on ports.
# Scope each source to its architecture before enabling dpkg multiarch.
test -f /etc/apt/sources.list
sed -i -E 's#^deb (http://(archive\.ubuntu\.com/ubuntu/|security\.ubuntu\.com/ubuntu/))#deb [arch=amd64] \1#' \
  /etc/apt/sources.list
cat > /etc/apt/sources.list.d/armhf-ports.list <<'APT_ARMHF'
deb [arch=armhf] http://ports.ubuntu.com/ubuntu-ports jammy main restricted universe multiverse
deb [arch=armhf] http://ports.ubuntu.com/ubuntu-ports jammy-updates main restricted universe multiverse
deb [arch=armhf] http://ports.ubuntu.com/ubuntu-ports jammy-security main restricted universe multiverse
deb [arch=armhf] http://ports.ubuntu.com/ubuntu-ports jammy-backports main restricted universe multiverse
APT_ARMHF
dpkg --add-architecture armhf
apt-get update -qq
apt-get install -y --no-install-recommends \
  ca-certificates git autoconf automake libtool pkg-config make \
  python3 binutils gcc-arm-linux-gnueabihf g++-arm-linux-gnueabihf \
  libc6-dev-armhf-cross libusb-1.0-0-dev:armhf libudev-dev:armhf

# Lock to the exact upstream source and the identical PLASMA native injection.
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
export CC=arm-linux-gnueabihf-gcc
export CXX=arm-linux-gnueabihf-g++
export AR=arm-linux-gnueabihf-ar
export RANLIB=arm-linux-gnueabihf-ranlib
export PKG_CONFIG_LIBDIR=/usr/lib/arm-linux-gnueabihf/pkgconfig:/usr/share/pkgconfig
export PKG_CONFIG_SYSROOT_DIR=/
unset PKG_CONFIG_PATH
./configure --build=x86_64-pc-linux-gnu --host=arm-linux-gnueabihf \
  --disable-werror --enable-internal-jimtcl --disable-internal-libjaylink
make -j2
test -x src/openocd
arm-linux-gnueabihf-readelf -h src/openocd | grep -Eq 'Machine:[[:space:]]+ARM'
cp src/openocd /cross-output/openocd
cp -a tcl /cross-output/tcl
CROSS
