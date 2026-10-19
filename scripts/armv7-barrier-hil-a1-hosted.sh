#!/usr/bin/env bash
# HIL-A1 immutable-container cross-build; GitHub-hosted only, no SWPC/Z2.
set -euo pipefail
test "$GITHUB_ACTIONS" = true
test "$RUNNER_ENVIRONMENT" = github-hosted
test "$GITHUB_REPOSITORY" = physicslu/plasma
[[ "$GITHUB_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$GITHUB_RUN_ID" =~ ^[0-9]+$ ]]
test -n "$RUNNER_TEMP"
test -n "$GITHUB_WORKSPACE"
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
test -z "$(printenv SSH_AUTH_SOCK || true)"

# The official Debian amd64 image digest is immutable. A date-specific
# Debian snapshot freezes compiler and binutils dependencies.
readonly IMAGE='debian:bookworm-20261005@sha256:bc49dc1918ee1a47a93e65b5e4676e8680fb754b133197b92ca52bfe6731d5f0'
readonly SNAPSHOT='20261005T000000Z'
readonly ROOT="$RUNNER_TEMP/plasma-armv7-hil-a1-$GITHUB_RUN_ID"
umask 077
mkdir -m 700 "$ROOT"

docker run --rm --platform linux/amd64 \
  --cap-drop=NET_RAW --security-opt no-new-privileges \
  --mount "type=bind,src=$GITHUB_WORKSPACE,dst=/plasma,readonly" \
  --mount "type=bind,src=$ROOT,dst=/out" \
  -e GITHUB_SHA="$GITHUB_SHA" \
  -e RUNNER_TEMP=/out \
  -e PLASMA_TOOLCHAIN_IMAGE="$IMAGE" \
  -e PLASMA_TOOLCHAIN_SNAPSHOT="$SNAPSHOT" \
  "$IMAGE" bash -euo pipefail -c '
    export DEBIAN_FRONTEND=noninteractive
    printf "%s\n" \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/$PLASMA_TOOLCHAIN_SNAPSHOT/ bookworm main" \
      > /etc/apt/sources.list
    rm -f /etc/apt/sources.list.d/debian.sources
    apt-get update -qq -o Acquire::Check-Valid-Until=false
    apt-get install -y -qq --no-install-recommends \
      python3 git gcc-arm-linux-gnueabihf binutils-arm-linux-gnueabihf libc6-dev-armhf-cross
    git config --global --add safe.directory /plasma
    python3 /plasma/scripts/armv7-barrier-hil-a1.py build \
      --output-dir /out/build --expected-sha "$GITHUB_SHA"
    test -s /out/build/libplasma_mmio_barrier.so
    test -s /out/build/receipt.json
    chmod -R a+rX /out/build
  '

test -f "$ROOT/build/receipt.json"
(cd "$ROOT/build" && sha256sum \
  libplasma_mmio_barrier.so receipt.json \
  elf-header.txt elf-attributes.txt elf-symbols.txt barrier-disassembly.txt \
  > SHA256SUMS)
echo "HIL-A1 GitHub-hosted ARMv7 cross-build: PASS; Z2: NOT_RUN"
