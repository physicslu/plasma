#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
console_root="${repo_root}/software/web/dist/standalone"
state_root="/tmp/plasma-render-control-station"
public_port="${PORT:-10000}"
manager_port="${PLASMA_RENDER_MANAGER_PORT:-18180}"
configured_ppu_alias="${PLASMA_RENDER_PPU_ALIAS:-z2like-qemu}"
ppu_alias="z2like-qemu"
ppu_endpoint="${PLASMA_RENDER_PPU_ENDPOINT:-}"
runtime_gateway_host="${PLASMA_RENDER_PPU_RUNTIME_GATEWAY_HOST:-172.30.77.2}"
ppu_access_client_id="${PLASMA_RENDER_PPU_ACCESS_CLIENT_ID:-}"
ppu_access_client_secret="${PLASMA_RENDER_PPU_ACCESS_CLIENT_SECRET:-}"
manager_pid=""
console_pid=""

if [[ "${configured_ppu_alias}" != "${ppu_alias}" ]]; then
  printf '[render-control-station] Ignoring deprecated PLASMA_RENDER_PPU_ALIAS=%s; canonical z2like-demo alias is %s\n' \
    "${configured_ppu_alias}" "${ppu_alias}" >&2
fi
if [[ ! "${public_port}" =~ ^[0-9]+$ ]] || (( public_port < 1 || public_port > 65535 )); then
  printf '[render-control-station] Invalid PORT: %s\n' "${public_port}" >&2
  exit 64
fi
if [[ ! "${manager_port}" =~ ^[0-9]+$ ]] || (( manager_port < 1 || manager_port > 65535 )); then
  printf '[render-control-station] Invalid manager port: %s\n' "${manager_port}" >&2
  exit 64
fi
if [[ -z "${ppu_endpoint}" ]]; then
  printf '[render-control-station] PLASMA_RENDER_PPU_ENDPOINT is required\n' >&2
  exit 78
fi
if [[ -n "${ppu_access_client_id}" || -n "${ppu_access_client_secret}" ]]; then
  if [[ -z "${ppu_access_client_id}" || -z "${ppu_access_client_secret}" ]]; then
    printf '[render-control-station] Cloudflare Access service identity requires both PLASMA_RENDER_PPU_ACCESS_CLIENT_ID and PLASMA_RENDER_PPU_ACCESS_CLIENT_SECRET\n' >&2
    exit 78
  fi
fi
if [[ ! -f "${console_root}/server.js" ]]; then
  printf '[render-control-station] Missing built Control Station runtime: %s/server.js\n' "${console_root}" >&2
  exit 69
fi

python - "${ppu_endpoint}" "${runtime_gateway_host}" <<'PY'
import ipaddress
import sys
from urllib.parse import urlsplit

value = sys.argv[1].strip()
parsed = urlsplit(value)
if parsed.scheme != "https" or not parsed.netloc or parsed.hostname is None:
    raise SystemExit("PLASMA_RENDER_PPU_ENDPOINT must be an absolute HTTPS URL")
if parsed.username is not None or parsed.password is not None:
    raise SystemExit("PLASMA_RENDER_PPU_ENDPOINT must not embed credentials")
if parsed.query or parsed.fragment:
    raise SystemExit("PLASMA_RENDER_PPU_ENDPOINT must not contain query or fragment")
if parsed.path not in {"", "/"}:
    raise SystemExit("PLASMA_RENDER_PPU_ENDPOINT must identify the managed PPU ingress root")

runtime_gateway_host = sys.argv[2]
if runtime_gateway_host != runtime_gateway_host.strip():
    raise SystemExit("PLASMA_RENDER_PPU_RUNTIME_GATEWAY_HOST must not contain surrounding whitespace")
try:
    address = ipaddress.ip_address(runtime_gateway_host)
except ValueError as exc:
    raise SystemExit("PLASMA_RENDER_PPU_RUNTIME_GATEWAY_HOST must be a private IPv4 address") from exc
if (
    address.version != 4
    or not address.is_private
    or address.is_loopback
    or address.is_unspecified
    or address.is_multicast
):
    raise SystemExit("PLASMA_RENDER_PPU_RUNTIME_GATEWAY_HOST must be a private non-loopback IPv4 address")
PY

# Cloudflare Access service identity is transport state, not Manager registry
# state. Keep the secret out of manager.yaml and scope it to this exact endpoint.
if [[ -n "${ppu_access_client_id}" ]]; then
  export PLASMA_MANAGER_CF_ACCESS_ORIGIN="${ppu_endpoint%/}"
  export PLASMA_MANAGER_CF_ACCESS_CLIENT_ID="${ppu_access_client_id}"
  export PLASMA_MANAGER_CF_ACCESS_CLIENT_SECRET="${ppu_access_client_secret}"
  printf '[render-control-station] Cloudflare Access service identity enabled for the configured PPU origin\n'
else
  unset PLASMA_MANAGER_CF_ACCESS_ORIGIN PLASMA_MANAGER_CF_ACCESS_CLIENT_ID PLASMA_MANAGER_CF_ACCESS_CLIENT_SECRET || true
fi

# Browser Runtime Deployment must never learn a direct Bootstrap endpoint. The
# Manager reuses the protected managed PPU origin and a fixed ingress prefix;
# SWPC alone maps that prefix to the independent QEMU Bootstrap :18081 service.
export PLASMA_MANAGER_BOOTSTRAP_TRANSPORT="managed-gateway-prefix-v1"
export PLASMA_MANAGER_BOOTSTRAP_RUNTIME_GATEWAY_HOST="${runtime_gateway_host}"

cleanup() {
  if [[ -n "${console_pid}" ]] && kill -0 "${console_pid}" 2>/dev/null; then
    kill "${console_pid}" 2>/dev/null || true
  fi
  if [[ -n "${manager_pid}" ]] && kill -0 "${manager_pid}" 2>/dev/null; then
    kill "${manager_pid}" 2>/dev/null || true
  fi
  wait "${console_pid}" "${manager_pid}" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' INT TERM

mkdir -p "${state_root}"
manager_config="${state_root}/manager.yaml"
registry_state="${state_root}/manager-registry.json"
observation_db="${state_root}/manager-observations.sqlite3"

# z2like-demo is a fixed-target public lab. The Manager keeps lifecycle state so
# the browser can execute the required commissioned -> disabled -> commissioned
# maintenance workflow and so Bootstrap pairing credentials can be device-bound
# and persisted separately. The public BFF is constrained to lifecycle-only
# mutation for the canonical alias; add/remove/endpoint mutation remain blocked.
python - "${manager_config}" "${manager_port}" "${observation_db}" "${registry_state}" "${ppu_alias}" "${ppu_endpoint}" <<'PY'
import sys
from pathlib import Path
import yaml

path, port, observation_db, registry_state, alias, endpoint = sys.argv[1:]
payload = {
    "manager": {
        "host": "127.0.0.1",
        "port": int(port),
        "request_timeout_s": 10.0,
        "poll_interval_s": 2.0,
        "observation_db_path": observation_db,
        "registry_state_path": registry_state,
    },
    "ppus": [{"alias": alias, "endpoint": endpoint}],
}
Path(path).write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
PY

printf '[render-control-station] Starting fixed-target Bootstrap-capable Plasma Manager on 127.0.0.1:%s for %s -> %s\n' \
  "${manager_port}" "${ppu_alias}" "${ppu_endpoint}"
# bootstrap_server composes the standard "python -m plasma_manager.server" behavior
# with the independent PPU Bootstrap policy routes.
python -m plasma_manager.bootstrap_server --config "${manager_config}" &
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
    raise SystemExit("Plasma Manager did not become ready")
PY

export HOST="0.0.0.0"
export PORT="${public_port}"
export PLASMA_FLEET_UI_ENABLED="1"
export PLASMA_CONTROL_STATION_MODE="managed"
export PLASMA_MANAGER_API_URL="http://127.0.0.1:${manager_port}"
export PLASMA_MANAGER_PPU_ALIAS="${ppu_alias}"
export PLASMA_MANAGER_REGISTRY_POLICY="fixed-lifecycle"
export PLASMA_DEPLOYMENT_IDENTITY_ENABLED="1"
export PLASMA_DEPLOYMENT_IDENTITY_SERVICE="plasma-control-station-lab"

printf '[render-control-station] Starting Control Station Console/BFF on 0.0.0.0:%s\n' "${public_port}"
cd "${console_root}"
node "${console_root}/server.js" &
console_pid=$!

set +e
wait -n "${manager_pid}" "${console_pid}"
service_status=$?
set -e
printf '[render-control-station] A Control Station process exited with status %s\n' "${service_status}" >&2
exit "${service_status}"