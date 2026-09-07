#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
console_root="${repo_root}/software/web/dist/standalone"
state_root="/tmp/plasma-render-control-station"
public_port="${PORT:-10000}"
manager_port="${PLASMA_RENDER_MANAGER_PORT:-18180}"
ppu_alias="${PLASMA_RENDER_PPU_ALIAS:-swpc-ppu}"
ppu_endpoint="${PLASMA_RENDER_PPU_ENDPOINT:-}"
manager_pid=""
console_pid=""

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
if [[ ! "${ppu_alias}" =~ ^[A-Za-z0-9._-]{1,128}$ ]]; then
  printf '[render-control-station] PLASMA_RENDER_PPU_ALIAS is invalid\n' >&2
  exit 64
fi
if [[ ! -f "${console_root}/server.js" ]]; then
  printf '[render-control-station] Missing built Control Station runtime: %s/server.js\n' "${console_root}" >&2
  exit 69
fi

python - "${ppu_endpoint}" <<'PY'
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
    raise SystemExit("PLASMA_RENDER_PPU_ENDPOINT must identify the restricted ingress root")
PY

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
observation_db="${state_root}/manager-observations.sqlite3"

# The public lab registry is deliberately immutable. Omitting
# manager.registry_state_path keeps add/remove/lifecycle mutation disabled and
# prevents an unauthenticated public Console/BFF caller from turning the fixed
# SWPC lab target into an arbitrary Manager-side HTTP(S) request target.
python - "${manager_config}" "${manager_port}" "${observation_db}" "${ppu_alias}" "${ppu_endpoint}" <<'PY'
import sys
from pathlib import Path
import yaml

path, port, observation_db, alias, endpoint = sys.argv[1:]
payload = {
    "manager": {
        "host": "127.0.0.1",
        "port": int(port),
        "request_timeout_s": 10.0,
        "poll_interval_s": 2.0,
        "observation_db_path": observation_db,
    },
    "ppus": [{"alias": alias, "endpoint": endpoint}],
}
Path(path).write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
PY

printf '[render-control-station] Starting immutable-registry Plasma Manager on 127.0.0.1:%s for %s -> %s\n' \
  "${manager_port}" "${ppu_alias}" "${ppu_endpoint}"
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
    raise SystemExit("Plasma Manager did not become ready")
PY

export HOST="0.0.0.0"
export PORT="${public_port}"
export PLASMA_FLEET_UI_ENABLED="1"
export PLASMA_CONTROL_STATION_MODE="managed"
export PLASMA_MANAGER_API_URL="http://127.0.0.1:${manager_port}"
export PLASMA_MANAGER_PPU_ALIAS="${ppu_alias}"

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
