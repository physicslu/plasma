#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_dir="${repo_root}/software/python"
config_path="${python_dir}/config/render-demo.yaml"
console_root="${repo_root}/software/web/dist/standalone"
state_root="/tmp/plasma-render"
public_port="${PORT:-10000}"
gateway_port="${PLASMA_RENDER_GATEWAY_PORT:-18080}"
manager_port="${PLASMA_RENDER_MANAGER_PORT:-18180}"
ppu_alias="${PLASMA_RENDER_PPU_ALIAS:-render-demo-ppu}"
flash_bytes="${PLASMA_RENDER_FLASH_BYTES:-1048576}"
engineering_enabled="${PLASMA_RENDER_ENGINEERING_MOCK:-1}"
catalog_manifest="${PLASMA_DEVICE_CATALOG_MANIFEST:-${repo_root}/data/device-catalog/production/icpn-v1-manifest.json}"
server_pid=""
gateway_pid=""
manager_pid=""
console_pid=""

for port_name in public_port gateway_port manager_port; do
  port_value="${!port_name}"
  if [[ ! "${port_value}" =~ ^[0-9]+$ ]] || (( port_value < 1 || port_value > 65535 )); then
    printf '[render-start] Invalid %s: %s\n' "${port_name}" "${port_value}" >&2
    exit 64
  fi
done
if [[ ! "${flash_bytes}" =~ ^[0-9]+$ ]] || (( flash_bytes < 1 )); then
  printf '[render-start] Invalid PLASMA_RENDER_FLASH_BYTES: %s\n' "${flash_bytes}" >&2
  exit 64
fi
if [[ "${engineering_enabled}" != "0" && "${engineering_enabled}" != "1" ]]; then
  printf '[render-start] PLASMA_RENDER_ENGINEERING_MOCK must be 0 or 1\n' >&2
  exit 64
fi
if [[ ! "${ppu_alias}" =~ ^[A-Za-z0-9._-]{1,128}$ ]]; then
  printf '[render-start] PLASMA_RENDER_PPU_ALIAS is invalid\n' >&2
  exit 64
fi
if [[ ! -f "${console_root}/server.js" ]]; then
  printf '[render-start] Missing built Control Station runtime: %s/server.js\n' "${console_root}" >&2
  exit 69
fi
if [[ ! -f "${catalog_manifest}" ]]; then
  printf '[render-start] Missing production Device Catalog manifest: %s\n' "${catalog_manifest}" >&2
  exit 69
fi
export PLASMA_DEVICE_CATALOG_MANIFEST="${catalog_manifest}"

# Fail closed before binding a public socket. This validates manifest identity,
# admitted-source Git blob bindings, canonical schemas, row counts and duplicate ICPNs.
python -m plasma_web.device_catalog --manifest "${catalog_manifest}" >/dev/null

cleanup() {
  for pid_name in console_pid manager_pid gateway_pid server_pid; do
    pid="${!pid_name}"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null || true
    fi
  done
  wait "${console_pid}" "${manager_pid}" "${gateway_pid}" "${server_pid}" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' INT TERM

mkdir -p "${state_root}/output" "${state_root}/logs" "${state_root}/engineering"
manager_config="${state_root}/manager.yaml"
observation_db="${state_root}/manager-observations.sqlite3"

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
  --host 127.0.0.1
  --port "${gateway_port}"
  --plasma-host 127.0.0.1
  --plasma-port 9900
  --output-root "${state_root}/output"
)
if [[ "${engineering_enabled}" == "1" ]]; then
  gateway_args+=(
    --engineering-mock
    --engineering-mock-root "${state_root}/engineering"
    --engineering-mock-flash-size "${flash_bytes}"
  )
fi

printf '[render-start] Starting loopback-only Mock PPU Plasma Gateway on 127.0.0.1:%s\n' "${gateway_port}"
python "${gateway_args[@]}" &
gateway_pid=$!

python - "${gateway_pid}" "${gateway_port}" <<'PY'
import json
import os
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

gateway_pid = int(sys.argv[1])
port = int(sys.argv[2])
deadline = time.monotonic() + 20
while time.monotonic() < deadline:
    try:
        os.kill(gateway_pid, 0)
        with urlopen(f"http://127.0.0.1:{port}/api/health/ready", timeout=1) as response:
            payload = json.loads(response.read())
        if payload.get("execution") == "ready":
            break
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        time.sleep(0.1)
else:
    raise SystemExit("[render-start] Mock PPU Plasma Gateway did not become ready")
PY

python - "${manager_config}" "${manager_port}" "${observation_db}" "${ppu_alias}" "${gateway_port}" <<'PY'
import sys
from pathlib import Path
import yaml

path, manager_port, observation_db, alias, gateway_port = sys.argv[1:]
payload = {
    "manager": {
        "host": "127.0.0.1",
        "port": int(manager_port),
        "request_timeout_s": 10.0,
        "poll_interval_s": 2.0,
        "observation_db_path": observation_db,
    },
    "ppus": [{"alias": alias, "endpoint": f"http://127.0.0.1:{int(gateway_port)}"}],
}
Path(path).write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
PY

printf '[render-start] Starting immutable-registry Plasma Manager on 127.0.0.1:%s for %s\n' \
  "${manager_port}" "${ppu_alias}"
python -m plasma_manager.server --config "${manager_config}" &
manager_pid=$!

python - "${manager_pid}" "${manager_port}" <<'PY'
import os
import socket
import sys
import time

pid = int(sys.argv[1])
port = int(sys.argv[2])
deadline = time.monotonic() + 15
while time.monotonic() < deadline:
    try:
        os.kill(pid, 0)
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            break
    except OSError:
        time.sleep(0.1)
else:
    raise SystemExit("[render-start] Plasma Manager did not become ready")
PY

export HOST="0.0.0.0"
export PORT="${public_port}"
export PLASMA_FLEET_UI_ENABLED="1"
export PLASMA_CONTROL_STATION_MODE="managed"
export PLASMA_MANAGER_API_URL="http://127.0.0.1:${manager_port}"
export PLASMA_MANAGER_PPU_ALIAS="${ppu_alias}"
export PLASMA_DEPLOYMENT_IDENTITY_ENABLED="1"
export PLASMA_DEPLOYMENT_IDENTITY_SERVICE="plasma-public-demo"

printf '[render-start] Starting public Control Station Console/BFF on 0.0.0.0:%s\n' "${public_port}"
cd "${console_root}"
node "${console_root}/server.js" &
console_pid=$!

set +e
wait -n "${server_pid}" "${gateway_pid}" "${manager_pid}" "${console_pid}"
service_status=$?
set -e
printf '[render-start] A Plasma demo process exited with status %s\n' "${service_status}" >&2
exit "${service_status}"
