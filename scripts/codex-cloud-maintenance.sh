#!/usr/bin/env bash
set -Eeuo pipefail

script_path="$(readlink -f "${BASH_SOURCE[0]}")"
repo="$(cd "$(dirname "$script_path")/.." && pwd)"

# A cached Cloud container may resume on a commit with changed lock files.
# Reuse the idempotent setup path so Python and Web dependencies match the checkout.
exec bash "$repo/scripts/codex-cloud-setup.sh"
