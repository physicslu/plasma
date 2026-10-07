#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 OUTPUT_DIR ARCHITECTURE" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output="$1"
architecture="$2"
metadata="$repo_root/release/openocd.json"

read -r version source_repository source_commit runtime_id < <(
  python3 - "$metadata" <<'PY'
import json,sys
payload=json.load(open(sys.argv[1], encoding='utf-8'))
print(payload['version'], payload['source_repository'], payload['source_commit'], payload['runtime_id'])
PY
)

expected_runtime_id="${version}-${source_commit:0:12}"
[[ "$runtime_id" == "$expected_runtime_id" ]] || {
  echo "release/openocd.json runtime_id mismatch: $runtime_id != $expected_runtime_id" >&2
  exit 2
}

case "$architecture" in
  x86_64)
    platform_name="linux/amd64"
    image="ubuntu:22.04"
    ;;
  armv7l)
    platform_name="linux/arm/v7"
    image="arm32v7/ubuntu:22.04"
    ;;
  *)
    echo "unsupported architecture: $architecture" >&2
    exit 2
    ;;
esac

rm -rf "$output"
mkdir -p "$output"

docker run --rm \
  --platform "$platform_name" \
  --volume "$repo_root:/repo:ro" \
  --volume "$output:/out" \
  --env OPENOCD_VERSION="$version" \
  --env OPENOCD_SOURCE_REPOSITORY="$source_repository" \
  --env OPENOCD_SOURCE_COMMIT="$source_commit" \
  --env OPENOCD_RUNTIME_ID="$runtime_id" \
  --env OPENOCD_ARCHITECTURE="$architecture" \
  "$image" \
  bash -euxo pipefail -c '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends \
      build-essential ca-certificates git autoconf automake libtool pkg-config python3

    prefix="/opt/plasma/programming-engines/openocd/${OPENOCD_RUNTIME_ID}"
    mkdir -p /tmp/openocd-src
    cd /tmp/openocd-src
    git init
    git remote add origin "$OPENOCD_SOURCE_REPOSITORY"
    git fetch --depth 1 origin "$OPENOCD_SOURCE_COMMIT"
    git checkout --detach FETCH_HEAD
    test "$(git rev-parse HEAD)" = "$OPENOCD_SOURCE_COMMIT"
    git submodule update --init --recursive --depth 1

    ./bootstrap
    ./configure \
      --prefix="$prefix" \
      --disable-werror \
      --disable-doxygen-html \
      --enable-dummy \
      --enable-remote-bitbang \
      --disable-jlink
    make -j2
    make install
    strip --strip-unneeded "$prefix/bin/openocd"

    "$prefix/bin/openocd" --version
    test -d "$prefix/share/openocd/scripts/target"
    test -d "$prefix/share/openocd/scripts/interface"
    ldd "$prefix/bin/openocd" | tee /tmp/openocd-ldd.txt
    ! grep -q "not found" /tmp/openocd-ldd.txt
    "$prefix/bin/openocd" \
      -s "$prefix/share/openocd/scripts" \
      -c "adapter driver dummy" \
      -c "shutdown"

    python3 /repo/scripts/openocd-runtime.py build \
      --prefix "$prefix" \
      --output-dir /out \
      --version "$OPENOCD_VERSION" \
      --source-commit "$OPENOCD_SOURCE_COMMIT" \
      --architecture "$OPENOCD_ARCHITECTURE"
  '

artifact="$output/plasma-openocd-$runtime_id-linux-$architecture.tar.gz"
test -f "$artifact"
test -f "$artifact.sha256"
python3 "$repo_root/scripts/openocd-runtime.py" verify "$artifact" --sidecar "$artifact.sha256"
