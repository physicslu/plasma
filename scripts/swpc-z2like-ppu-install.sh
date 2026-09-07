#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
usage: sudo bash scripts/swpc-z2like-ppu-install.sh \
  --plasma-python /opt/plasma/python/<version>/bin/python3 \
  --ppu-id swpc-z2like-01 \
  --facility-id lab

Installs a PS-only, closed-hardware PPU surrogate on SWPC using the same
filesystem and systemd ownership model as the Z2 PS installer. This is an
x86_64 integration surrogate, not ARMv7/Z2 qualification evidence.
EOF
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
plasma_python=""
ppu_id=""
facility_id=""
proxy_port="18081"
nginx_marker="# Managed by Plasma SWPC Z2-like lab installer"

while (($#)); do
  case "$1" in
    --plasma-python) plasma_python="${2:-}"; shift 2 ;;
    --ppu-id) ppu_id="${2:-}"; shift 2 ;;
    --facility-id) facility_id="${2:-}"; shift 2 ;;
    --proxy-port) proxy_port="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; usage >&2; exit 64 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  printf 'swpc-z2like-ppu-install: run with sudo/root\n' >&2
  exit 77
fi
for value in "$plasma_python" "$ppu_id" "$facility_id"; do
  [[ -n "$value" ]] || { usage >&2; exit 64; }
done
if [[ "$plasma_python" != /opt/plasma/python/*/bin/python3 ]]; then
  printf 'swpc-z2like-ppu-install: --plasma-python must be Plasma-owned under /opt/plasma/python/<version>/bin/python3\n' >&2
  exit 78
fi
if [[ ! -x "$plasma_python" ]]; then
  printf 'swpc-z2like-ppu-install: Plasma Python is not executable: %s\n' "$plasma_python" >&2
  exit 78
fi
if [[ ! "$proxy_port" =~ ^[0-9]+$ ]] || (( proxy_port < 1 || proxy_port > 65535 || proxy_port == 9900 || proxy_port == 18080 )); then
  printf 'swpc-z2like-ppu-install: invalid restricted proxy port: %s\n' "$proxy_port" >&2
  exit 64
fi
if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
  printf 'swpc-z2like-ppu-install: repository must be clean for qualification staging\n' >&2
  exit 78
fi
for command in git ss systemctl nginx install useradd; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'swpc-z2like-ppu-install: required host command is missing: %s\n' "$command" >&2
    exit 69
  }
done

nginx_conf="/etc/nginx/conf.d/plasma-swpc-z2like-ppu.conf"
if [[ -e "$nginx_conf" ]] && ! grep -Fxq "$nginx_marker" "$nginx_conf"; then
  printf 'swpc-z2like-ppu-install: refusing to overwrite unmanaged Nginx config: %s\n' "$nginx_conf" >&2
  exit 78
fi

for port in 9900 18080 "$proxy_port"; do
  if ss -H -ltn "sport = :$port" | grep -q .; then
    printf 'swpc-z2like-ppu-install: TCP port %s is already in use; stop or migrate the owning service explicitly before installation\n' "$port" >&2
    ss -H -ltnp "sport = :$port" >&2 || true
    exit 78
  fi
done

read -r py_version py_releaselevel py_machine < <("$plasma_python" - <<'PY'
import platform, sys
print(".".join(map(str, sys.version_info[:3])), sys.version_info.releaselevel, platform.machine())
PY
)
"$plasma_python" - <<'PY'
import re
import sys

if sys.version_info < (3, 11) or sys.version_info.releaselevel != "final":
    raise SystemExit("Plasma Python must be a final release >= 3.11")
if sys.prefix == sys.base_prefix:
    raise SystemExit(
        "Plasma Python must be an isolated virtual environment; "
        "base or externally-managed interpreters are not accepted"
    )
try:
    import yaml
except ModuleNotFoundError as exc:
    raise SystemExit("Plasma Python must have PyYAML>=6.0 pre-provisioned") from exc
match = re.match(r"^(\d+)\.(\d+)", yaml.__version__)
if match is None or tuple(map(int, match.groups())) < (6, 0):
    raise SystemExit(f"Plasma Python requires PyYAML>=6.0, found {yaml.__version__}")
PY

sha="$(git -C "$repo_root" rev-parse HEAD)"
version="$("$plasma_python" - "$repo_root/release/product.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["product_version"])
PY
)"
release_id="${version}-${sha:0:12}"
release_dir="/opt/plasma/releases/${release_id}"
runtime_dir="${release_dir}/runtime"
config_path="/etc/plasma/ppu.yaml"
state_root="/var/lib/plasma"
log_root="/var/log/plasma"

printf '[swpc-z2like] release_id=%s source_sha=%s python=%s machine=%s\n' \
  "$release_id" "$sha" "$py_version" "$py_machine"

# The deployed interpreter is pre-provisioned and must not be mutated here.
# Build and execute with the same isolated interpreter.
tmp_runtime="$(mktemp -d /tmp/plasma-swpc-z2like-runtime.XXXXXX)"
trap 'rm -rf "$tmp_runtime"' EXIT
rm -rf "$tmp_runtime/runtime"
"$plasma_python" "$repo_root/scripts/ppu-runtime.py" build --output-dir "$tmp_runtime/runtime"
"$plasma_python" "$repo_root/scripts/ppu-runtime.py" validate "$tmp_runtime/runtime"

if id plasma >/dev/null 2>&1; then
  [[ "$(id -gn plasma)" == "plasma" ]] || { printf 'existing plasma account has unexpected primary group\n' >&2; exit 78; }
else
  useradd --system --home-dir /var/lib/plasma --shell /usr/sbin/nologin --user-group plasma
fi

install -d -m 0755 /opt/plasma/releases /opt/plasma/install /etc/plasma
install -d -m 0750 -o plasma -g plasma "$state_root" "$state_root/output" "$state_root/gateway-output" "$log_root"
if [[ -e "$release_dir" ]]; then
  printf 'swpc-z2like-ppu-install: immutable release already exists: %s\n' "$release_dir" >&2
  exit 78
fi
install -d -m 0755 "$release_dir"
cp -a "$tmp_runtime/runtime" "$runtime_dir"
chown -R root:root "$release_dir"
find "$release_dir" -type d -exec chmod 0755 {} +
find "$release_dir" -type f -exec chmod 0644 {} +

cat >"$config_path" <<EOF
ppu:
  id: "$ppu_id"
  facility_id: "$facility_id"
  model: "SWPC-Z2-SURROGATE"
  display_name: "SWPC Z2-like PS-only PPU"

server:
  host: 127.0.0.1
  port: 9900
  max_supported_sites: 8
  max_concurrent_jobs: 1
  max_queue_depth_per_site: 16
  output_root: $state_root/output
  log_root: $log_root
  max_metadata_bytes: 65536
  max_map_bytes: 1048576
  max_binary_bytes: 67108864

sites: []
EOF
chmod 0644 "$config_path"
chown root:root "$config_path"

catalog="/opt/plasma/current/runtime/data/device-catalog/production/icpn-v1-manifest.json"
app="/opt/plasma/current/runtime/ppu/ppu.pyz"
cat >/etc/systemd/system/plasma-server.service <<EOF
[Unit]
Description=Plasma PPU Programming Server
After=network.target

[Service]
Type=simple
User=plasma
Group=plasma
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=$state_root $log_root
Environment=PYTHONUNBUFFERED=1
Environment=PLASMA_DEVICE_CATALOG_MANIFEST=$catalog
ExecStart=$plasma_python $app server --config $config_path

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/plasma-web.service <<EOF
[Unit]
Description=Plasma Gateway
After=network-online.target plasma-server.service
Wants=network-online.target
Requires=plasma-server.service

[Service]
Type=simple
User=plasma
Group=plasma
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=$state_root $log_root
Environment=PYTHONUNBUFFERED=1
Environment=PLASMA_DEVICE_CATALOG_MANIFEST=$catalog
ExecStart=$plasma_python $app gateway --host 127.0.0.1 --port 18080 --plasma-host 127.0.0.1 --plasma-port 9900 --output-root $state_root/gateway-output

[Install]
WantedBy=multi-user.target
EOF
chmod 0644 /etc/systemd/system/plasma-server.service /etc/systemd/system/plasma-web.service

# The public tunnel must terminate on this restricted proxy, never on :18080.
cat >"$nginx_conf" <<EOF
$nginx_marker
server {
    listen 127.0.0.1:$proxy_port;
    server_name _;

    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Forwarded-Proto https;

    location = /api/health/live {
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:18080;
    }
    location = /api/health/ready {
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:18080;
    }
    location = /api/node {
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:18080;
    }
    location = /api/status {
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:18080;
    }
    location = /api/engineering/diagnostics/loopback {
        limit_except POST { deny all; }
        proxy_pass http://127.0.0.1:18080;
    }
    location / { return 404; }
}
EOF

ln -sfn "$release_dir" /opt/plasma/current.new
mv -Tf /opt/plasma/current.new /opt/plasma/current

systemctl daemon-reload
systemctl enable --now plasma-server.service plasma-web.service
nginx -t
systemctl reload nginx

"$plasma_python" - <<'PY'
import json
import time
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
deadline = time.monotonic() + 10.0
last_error = "readiness was not attempted"
while True:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SystemExit(f"PPU readiness failed after 10s: {last_error}")
    try:
        with opener.open(
            "http://127.0.0.1:18080/api/health/ready",
            timeout=min(1.0, max(0.1, remaining)),
        ) as response:
            payload = json.load(response)
        if response.status == 200 and payload.get("ok") is True and payload.get("execution") == "ready":
            print(json.dumps(payload, sort_keys=True))
            break
        last_error = f"unexpected readiness response: status={response.status} payload={payload!r}"
    except Exception as exc:
        last_error = f"{type(exc).__name__}: {exc}"
    time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
PY

cat >/opt/plasma/install/last-swpc-z2like-install.json <<EOF
{
  "schema_version": 1,
  "role": "ppu-surrogate",
  "platform": "linux",
  "architecture": "$py_machine",
  "z2_equivalent": false,
  "product_version": "$version",
  "git_sha": "$sha",
  "release_id": "$release_id",
  "plasma_python": "$plasma_python",
  "plasma_python_version": "$py_version",
  "gateway_bind": "127.0.0.1:18080",
  "restricted_ingress": "127.0.0.1:$proxy_port",
  "hardware_boundary": "closed",
  "configured_site_count": 0,
  "max_supported_sites": 8
}
EOF
chmod 0644 /opt/plasma/install/last-swpc-z2like-install.json

printf '[swpc-z2like] PASS: local PPU ready; restricted ingress is http://127.0.0.1:%s\n' "$proxy_port"
printf '[swpc-z2like] Cloudflare Tunnel must target the restricted ingress, never 127.0.0.1:18080\n'
