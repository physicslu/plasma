#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_dir="${repo_root}/software/python"
config_path="${python_dir}/config/render-demo.yaml"
static_root="${repo_root}/software/web/dist-render"
state_root="/tmp/plasma-render"
public_port="${PORT:-10000}"
flash_bytes="${PLASMA_RENDER_FLASH_BYTES:-1048576}"
engineering_enabled="${PLASMA_RENDER_ENGINEERING_MOCK:-1}"
catalog_path="${PLASMA_DEVICE_CATALOG_PATH:-${repo_root}/data/device-catalog/research/openocd-parts-canonical.csv}"
server_pid=""
gateway_pid=""

if [[ ! "${public_port}" =~ ^[0-9]+$ ]] || (( public_port < 1 || public_port > 65535 )); then
  printf '[render-start] Invalid PORT: %s\n' "${public_port}" >&2
  exit 64
fi
if [[ ! "${flash_bytes}" =~ ^[0-9]+$ ]] || (( flash_bytes < 1 )); then
  printf '[render-start] Invalid PLASMA_RENDER_FLASH_BYTES: %s\n' "${flash_bytes}" >&2
  exit 64
fi
if [[ "${engineering_enabled}" != "0" && "${engineering_enabled}" != "1" ]]; then
  printf '[render-start] PLASMA_RENDER_ENGINEERING_MOCK must be 0 or 1\n' >&2
  exit 64
fi
if [[ ! -f "${static_root}/index.html" ]]; then
  printf '[render-start] Missing built Web Console: %s/index.html\n' "${static_root}" >&2
  exit 69
fi
if [[ ! -f "${catalog_path}" ]]; then
  printf '[render-start] Missing Device Catalog: %s\n' "${catalog_path}" >&2
  exit 69
fi
export PLASMA_DEVICE_CATALOG_PATH="${catalog_path}"

cleanup() {
  if [[ -n "${gateway_pid}" ]] && kill -0 "${gateway_pid}" 2>/dev/null; then
    kill "${gateway_pid}" 2>/dev/null || true
  fi
  if [[ -n "${server_pid}" ]] && kill -0 "${server_pid}" 2>/dev/null; then
    kill "${server_pid}" 2>/dev/null || true
  fi
  wait "${gateway_pid}" "${server_pid}" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' INT TERM

mkdir -p "${state_root}/output" "${state_root}/logs" "${state_root}/engineering"

# This metadata is public by design. Render supplies RENDER_GIT_COMMIT and
# RENDER_GIT_BRANCH at runtime; exposing only those non-secret values lets an
# external smoke test prove which source revision is actually serving traffic.
python - "${static_root}/deployment.json" <<'PY'
import json
import os
import sys
from pathlib import Path

payload = {
    "schema_version": 1,
    "service": "plasma-public-demo",
    "platform": "render" if os.environ.get("RENDER") == "true" else "local",
    "git_commit": os.environ.get("RENDER_GIT_COMMIT") or None,
    "git_branch": os.environ.get("RENDER_GIT_BRANCH") or None,
}
Path(sys.argv[1]).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

printf '[render-start] Starting localhost-only Plasma Protocol v3.3 Server\n'
python -m plasma_server.server --config "${config_path}" &
server_pid=$!

python - "${server_pid}" <<'PY'
import os
import socket
import sys
import time

server_pid = int(sys.argv[1])
deadline = time.monotonic() + 15
while time.monotonic() < deadline:
    try:
        os.kill(server_pid, 0)
        with socket.create_connection(("127.0.0.1", 9900), timeout=0.5):
            break
    except OSError:
        time.sleep(0.1)
else:
    raise SystemExit("[render-start] Plasma Server did not become ready on 127.0.0.1:9900")
PY

gateway_args=(
  -m plasma_web.gateway
  --host 0.0.0.0
  --port "${public_port}"
  --plasma-host 127.0.0.1
  --plasma-port 9900
  --output-root "${state_root}/output"
  --static-root "${static_root}"
)
if [[ "${engineering_enabled}" == "1" ]]; then
  gateway_args+=(
    --engineering-mock
    --engineering-mock-root "${state_root}/engineering"
    --engineering-mock-flash-size "${flash_bytes}"
  )
fi

printf '[render-start] Starting same-origin Plasma Gateway on 0.0.0.0:%s\n' "${public_port}"
python "${gateway_args[@]}" &
gateway_pid=$!

set +e
wait -n "${server_pid}" "${gateway_pid}"
service_status=$?
set -e
printf '[render-start] A Plasma service exited with status %s\n' "${service_status}" >&2
exit "${service_status}"
