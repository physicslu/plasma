#!/usr/bin/env bash
# Acquire a *pinned* PYNQ-Z2 Board Repository in the ignored project build area.
# Print ONLY the repository directory on stdout for shell command substitution.
# Never changes Vivado's installation or global/user Board Store configuration.
set -Eeuo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
source_url="https://github.com/xupsh/pynq-supported-board-file.git"
source_commit="e02d6a3866b5465218f777168cdc51344ac94e07"
base_dir="$repo_root/pl/build/z2-swd-gpio"
cache="$base_dir/board-repository"
mkdir -p "$base_dir"

if [[ ! -d "$cache" ]]; then
  tmp="$(mktemp -d "$base_dir/.board-repo-fetch.XXXXXXXX")"
  trap 'rm -rf -- "$tmp"' EXIT
  echo "Fetching pinned PYNQ-Z2 Board Files $source_commit" >&2
  git clone --quiet "$source_url" "$tmp/source"
  git -C "$tmp/source" checkout --quiet --detach "$source_commit"
  if ! mv -T -- "$tmp/source" "$cache"; then
    echo "BOARD_REPO_FAIL: could not atomically place board repository" >&2
    exit 2
  fi
fi

if [[ ! -d "$cache/.git" ]]; then
  echo "BOARD_REPO_FAIL: existing cache is not a Git checkout: $cache" >&2
  exit 2
fi
actual="$(git -C "$cache" rev-parse HEAD)"
if [[ "$actual" != "$source_commit" ]]; then
  echo "BOARD_REPO_FAIL: pinned Git SHA mismatch: $actual" >&2
  exit 2
fi
if [[ -n "$(git -C "$cache" status --porcelain --untracked-files=no)" ]]; then
  echo "BOARD_REPO_FAIL: tracked Board Files were modified" >&2
  exit 2
fi
for file in board.xml preset.xml part0_pins.xml; do
  if [[ ! -f "$cache/pynq-z2/A.0/$file" ]]; then
    echo "BOARD_REPO_FAIL: missing PYNQ-Z2 $file" >&2
    exit 2
  fi
done
echo "$cache"
