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
ic_support_root="${PLASMA_IC_SUPPORT_ROOT:-${repo_root}/data/ic-support}"
runtime_evidence_root="${PLASMA_RUNTIME_EVIDENCE_ROOT:-${repo_root}}"
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
if [[ ! -d "${ic_support_root}/profiles" || ! -d "${ic_support_root}/bindings" ]]; then
  printf '[render-start] Missing repository-owned IC Support data root: %s\n' "${ic_support_root}" >&2
  exit 69
fi
export PLASMA_DEVICE_CATALOG_MANIFEST="${catalog_manifest}"
if [[ ! -d "${runtime_evidence_root}" ]]; then
  printf '[render-start] Missing full source-evidence root: %s\n' "${runtime_evidence_root}" >&2
  exit 69
fi
export PLASMA_RUNTIME_EVIDENCE_ROOT="${runtime_evidence_root}"
export PLASMA_IC_SUPPORT_ROOT="${ic_support_root}"

# Fail closed before binding a public socket. These checks validate the two
# repository-owned data roots used by the public Device Selector runtime.
python -m plasma_web.device_catalog --manifest "${catalog_manifest}" >/dev/null
python -m plasma_core.ic_support --summary >/dev/null

# A complete Render checkout must never silently omit H5/C5 candidate metadata.
# All records are source-only; preflight does not activate execution routes.
python - <<'PY'
from plasma_web.runtime_evidence_root import default_runtime_evidence_root
from plasma_web.backend_candidate_registry import get_default_backend_candidate_registry
from plasma_web.backend_source_reference import default_pinned_upstream
from plasma_web.openocd_provider_registry import get_default_openocd_provider_registry

root = default_runtime_evidence_root()
if root is None or not root.is_dir():
    raise SystemExit("[render-start] explicit OpenOCD source-evidence root unavailable")
if get_default_backend_candidate_registry().size != 362:
    raise SystemExit("[render-start] H5/C5 research candidates not fully present")
provider = get_default_openocd_provider_registry()
if provider is None or provider.inventory != {
    "openocd-upstream": 4176,
    "openocd-st-h5-research": 190,
    "openocd-st-c5-stldr-research": 172,
}:
    raise SystemExit("[render-start] source-only OpenOCD provider inventory missing")
if default_pinned_upstream() is None:
    raise SystemExit("[render-start] pinned OpenOCD source reference missing")
PY


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

with urlopen(
    f"http://127.0.0.1:{port}/api/devices/search?q=STM32F103C8T6&limit=1",
    timeout=2,
) as response:
    selected_payload = json.loads(response.read())
results = selected_payload.get("results")
if not isinstance(results, list) or len(results) != 1:
    raise SystemExit("[render-start] IC Selector runtime contract did not return STM32F103C8T6")
result = results[0]
selected_profile = result.get("selected_profile")
if result.get("icpn") != "STM32F103C8T6" or not isinstance(selected_profile, dict):
    raise SystemExit("[render-start] IC Selector runtime contract is missing selected_profile")
if selected_profile.get("icpn") != "STM32F103C8T6":
    raise SystemExit("[render-start] IC Selector selected_profile identity mismatch")

# A green STM32 smoke can hide the NXP installed-wheel evidence path bug.
# Public customer search must expose L1+ only; MCX L0 evidence is verified
# through the internal canonical resolver and must not leak through the public API.
with urlopen(
    f"http://127.0.0.1:{port}/api/devices/search?q=MKL25Z128VFM4&levels=1&limit=1",
    timeout=3,
) as response:
    nxp_search = json.loads(response.read())
nxp_rows = nxp_search.get("results")
if not isinstance(nxp_rows, list) or len(nxp_rows) != 1:
    raise SystemExit("[render-start] NXP L1 ICPN search unexpectedly empty")
nxp = nxp_rows[0]
if (nxp.get("vendor") != "NXP"
        or nxp.get("icpn") != "MKL25Z128VFM4"
        or nxp.get("catalog_level") != 1
        or nxp.get("job_selectable") is not False):
    raise SystemExit("[render-start] NXP L1 customer visibility boundary drift")

with urlopen(
    f"http://127.0.0.1:{port}/api/devices/search?q=MCXA132VFM&limit=1",
    timeout=3,
) as response:
    mcx_public = json.loads(response.read())
if mcx_public.get("total_count") != 0 or mcx_public.get("results") != []:
    raise SystemExit("[render-start] internal-only NXP L0 leaked into public IC Selector")

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.nxp_manufacturer_device_evidence import get_default_nxp_manufacturer_device_evidence

mcx_record = get_default_device_catalog().resolve("NXP", "MCXA132VFM")
if mcx_record is None:
    raise SystemExit("[render-start] internal NXP L0 identity unavailable")
evidence = get_default_nxp_manufacturer_device_evidence().resolve_exact(mcx_record)
if not isinstance(evidence, dict) or evidence.get("icpn") != "MCXA132VFM":
    raise SystemExit("[render-start] installed NXP internal evidence path is broken")
for exact, provider_id in (
    ("STM32H503CBT6", "openocd-st-h5-research"),
    ("STM32C531CBT6", "openocd-st-c5-stldr-research"),
):
    with urlopen(
        f"http://127.0.0.1:{port}/api/devices/search?q={exact}&limit=1",
        timeout=3,
    ) as response:
        source_search = json.loads(response.read())
    row = source_search.get("results", [None])[0]
    if not isinstance(row, dict) or row.get("icpn") != exact:
        raise SystemExit(f"[render-start] Source-only lookup missing for {exact}")
    candidate = row.get("backend_candidate")
    providers = row.get("backend_providers")
    source_ref = row.get("backend_source_reference")
    if (row.get("catalog_level") != 1
            or row.get("job_selectable") is not False
            or row["backend"]["mapping_status"] != "no_mapping"
            or not isinstance(candidate, dict)
            or candidate.get("provider_id") != provider_id
            or candidate.get("executable") is not False
            or candidate.get("hardware_runtime_ready") is not False
            or not isinstance(source_ref, dict)
            or source_ref.get("provider_id") != provider_id
            or not isinstance(providers, list) or len(providers) != 1
            or providers[0].get("provider_id") != provider_id
            or providers[0].get("executable") is not False
            or providers[0].get("installed_binary_sha256") is not None):
        raise SystemExit(f"[render-start] H5/C5 pinned display metadata unavailable: {exact}")
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
