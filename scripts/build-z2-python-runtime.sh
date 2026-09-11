#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 OUTPUT_DIR" >&2
  exit 2
fi

: "${PYTHON_VERSION:?PYTHON_VERSION is required}"
: "${PYTHON_SOURCE_SHA256:?PYTHON_SOURCE_SHA256 is required}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output="$1"

rm -rf "$output"
mkdir -p "$output"

docker run --rm \
  --platform linux/arm/v7 \
  --volume "$repo_root:/repo:ro" \
  --volume "$output:/out" \
  --env PYTHON_VERSION="$PYTHON_VERSION" \
  --env PYTHON_SOURCE_SHA256="$PYTHON_SOURCE_SHA256" \
  arm32v7/ubuntu:22.04 \
  bash -euxo pipefail -c '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends \
      build-essential ca-certificates curl xz-utils \
      libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
      libsqlite3-dev libffi-dev liblzma-dev uuid-dev
    curl --fail --silent --show-error --location \
      "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tar.xz" \
      --output /tmp/Python.tar.xz
    printf "%s  %s\n" "$PYTHON_SOURCE_SHA256" /tmp/Python.tar.xz | sha256sum --check -
    mkdir -p /tmp/python-src
    tar -xJf /tmp/Python.tar.xz -C /tmp/python-src --strip-components=1
    cd /tmp/python-src
    ./configure \
      --prefix="/opt/plasma/python/${PYTHON_VERSION}" \
      --with-ensurepip=install
    make -j2
    make altinstall
    minor="${PYTHON_VERSION%.*}"
    ln -s "python${minor}" "/opt/plasma/python/${PYTHON_VERSION}/bin/python3"
    "/opt/plasma/python/${PYTHON_VERSION}/bin/python3" -c \
      "import ssl,sqlite3,urllib.request; print(ssl.OPENSSL_VERSION, sqlite3.sqlite_version)"
    "/opt/plasma/python/${PYTHON_VERSION}/bin/python3" \
      /repo/scripts/z2-python-runtime.py build \
      --python-root "/opt/plasma/python/${PYTHON_VERSION}" \
      --output-dir /out \
      --source-ref "python.org/Python-${PYTHON_VERSION}.tar.xz#sha256=${PYTHON_SOURCE_SHA256}"
  '
