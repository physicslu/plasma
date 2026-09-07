# Render Control Station -> SWPC Z2-like PPU Managed PS Loopback

> Status: **integration qualification foundation**. This path validates the public managed software route before real PYNQ-Z2 deployment. It does not make ARMv7, Z2, FPGA, Site I/O, target-power, or real-IC claims.

## 1. Purpose

The qualification topology is:

```text
Browser
  -> Render plasma-control-station-lab
       -> source-tree-independent Console / same-origin BFF
       -> Plasma Manager on 127.0.0.1:18180
       -> HTTPS restricted PPU ingress
  -> Cloudflare Tunnel
  -> SWPC restricted Nginx ingress on 127.0.0.1:18081
       -> allowlisted diagnostics/status routes only
       -> SWPC Plasma Gateway on 127.0.0.1:18080
       -> SWPC Plasma Server on 127.0.0.1:9900
       -> PS diagnostic handler
       -> return
```

The existing `plasma-public-demo` Render service remains independent and continues to host the public Mock demo. The new `plasma-control-station-lab` service is a Control Station role and does not start a local PPU Server/Gateway.

## 2. Evidence boundary

The SWPC surrogate intentionally mirrors the Z2 PS software ownership model:

```text
/opt/plasma/python/<version>/bin/python3
/opt/plasma/releases/<release-id>/runtime
/opt/plasma/current
/opt/plasma/install/
/etc/plasma/ppu.yaml
/var/lib/plasma/
/var/log/plasma/
/etc/systemd/system/plasma-server.service
/etc/systemd/system/plasma-web.service
```

It also preserves:

- Plasma-owned final Python >= 3.11;
- system-level systemd;
- Plasma service user/group;
- `max_supported_sites = 8`;
- `sites: []` / configured `site_count = 0`;
- closed hardware boundary;
- Server on `127.0.0.1:9900`;
- Gateway on `127.0.0.1:18080`;
- immutable release identity `<product-version>-<git-sha-prefix12>`.

Intentional differences from real Z2:

| Dimension | SWPC surrogate | Real Z2 |
|---|---|---|
| CPU/ABI | x86_64 | ARMv7 |
| PYNQ ownership | absent | PYNQ System Python 3.10.x + PYNQ runtime |
| Gateway exposure | loopback-only, restricted reverse proxy | explicit Z2 LAN IPv4 during Z2 qualification |
| Hardware | closed | still closed for PS-only qualification, later PS/PL separately |
| Qualification claim | managed software/network path only | real Z2 PS deployment when separately qualified |

Therefore a SWPC PASS must never be reported as Z2 HIL PASS.

## 3. Render Control Station contract

`render.yaml` declares a separate service:

```text
plasma-control-station-lab
```

It requires the Render environment value:

```text
PLASMA_RENDER_PPU_ENDPOINT=https://<restricted-swpc-ppu-hostname>
```

and defaults to:

```text
PLASMA_RENDER_PPU_ALIAS=swpc-ppu
```

`scripts/render-control-station-start.sh` fails closed unless the PPU endpoint is an absolute HTTPS root URL with no embedded credentials, query, fragment, or nested path. The Manager itself remains loopback-only inside the Render service. The Console/BFF receives:

```text
PLASMA_FLEET_UI_ENABLED=1
PLASMA_CONTROL_STATION_MODE=managed
PLASMA_MANAGER_API_URL=http://127.0.0.1:18180
PLASMA_MANAGER_PPU_ALIAS=swpc-ppu
```

Render's service health check uses `/` deliberately. PPU reachability is a managed dependency and must not cause Render to continuously restart the Control Station when the laboratory SWPC is offline. PPU status and loopback are validated separately.

## 4. SWPC preparation

Before host mutation:

```bash
cd "$PLASMA_REPO"
git status -sb
git branch --show-current
git log -1 --oneline
git fetch origin main
```

For qualification, use a clean checkout at the intended exact source SHA.

The SWPC Plasma interpreter must already exist under the product-owned path, for example:

```text
/opt/plasma/python/3.11.16/bin/python3
```

Do not silently substitute `/usr/bin/python3` or the repository development venv as the deployed service interpreter.

Verify:

```bash
/opt/plasma/python/<version>/bin/python3 --version
/opt/plasma/python/<version>/bin/python3 - <<'PY'
import platform, sys
print(sys.version)
print(sys.version_info.releaselevel)
print(platform.machine())
PY
```

The interpreter must be a final Python >= 3.11. The expected SWPC machine architecture is x86_64; that result is recorded as a surrogate difference rather than rewritten as ARMv7.

## 5. Install the SWPC Z2-like PS-only surrogate

Run:

```bash
sudo bash scripts/swpc-z2like-ppu-install.sh \
  --plasma-python /opt/plasma/python/<version>/bin/python3 \
  --ppu-id swpc-z2like-01 \
  --facility-id lab
```

The installer refuses a dirty Git source tree, builds/validates the source-tree-independent PPU runtime, creates an immutable release directory, installs PS-only configuration and systemd services, activates `/opt/plasma/current`, verifies local Gateway readiness, and writes:

```text
/opt/plasma/install/last-swpc-z2like-install.json
```

The helper deliberately records:

```json
"z2_equivalent": false
```

because the surrogate does not prove ARMv7/PYNQ behavior.

## 6. Restricted public ingress

The helper keeps the actual Plasma Gateway private:

```text
127.0.0.1:18080
```

and installs an Nginx listener on:

```text
127.0.0.1:18081
```

Only these routes are exposed through that listener:

```text
GET  /api/health/live
GET  /api/health/ready
GET  /api/node
GET  /api/status
POST /api/engineering/diagnostics/loopback
```

Every other path returns `404` before reaching Plasma Gateway. The Cloudflare Tunnel must target the restricted listener:

```text
http://127.0.0.1:18081
```

It must **not** target `127.0.0.1:18080`.

This makes the public experiment a PS diagnostic/status surface, not a public programming command plane.

## 7. SWPC local acceptance

Verify:

```bash
readlink -f /opt/plasma/current
cat /opt/plasma/install/last-swpc-z2like-install.json
sudo systemctl --no-pager --full status plasma-server.service plasma-web.service
curl --noproxy '*' -fsS http://127.0.0.1:18080/api/health/ready
curl --noproxy '*' -fsS http://127.0.0.1:18081/api/node
curl --noproxy '*' -fsS http://127.0.0.1:18081/api/status
```

Confirm a forbidden route is blocked at the restricted ingress, for example:

```bash
curl --noproxy '*' -i http://127.0.0.1:18081/api/settings/sites
```

Expected result: `404`.

## 8. Configure Render

Set the `plasma-control-station-lab` environment variable to the Cloudflare HTTPS hostname that terminates on the restricted SWPC listener:

```text
PLASMA_RENDER_PPU_ENDPOINT=https://<restricted-swpc-ppu-hostname>
```

Do not use the existing public Preview/Mock hostname as a PPU endpoint unless it is explicitly configured as this restricted ingress. Render Manager accepts HTTP(S) PPU roots generally, but this public laboratory service deliberately requires HTTPS.

## 9. Public managed acceptance

First verify fleet observation from the public Control Station. Then run the canonical managed PS loopback against the Render origin:

```bash
python3 scripts/runtime_acceptance/run.py ps-loopback \
  --base-url https://<plasma-control-station-lab>.onrender.com/api/manager/ppu \
  --environment render-swpc-managed-ps
```

A PASS supports the claim:

```text
Render Control Station
  -> same-origin BFF
  -> Render Manager
  -> public HTTPS restricted route
  -> SWPC PS-only PPU surrogate
  -> PS diagnostic handler
  -> return
```

It does not support the claims:

```text
PYNQ-Z2 native deployment
ARMv7 ABI/runtime
PYNQ regression
PS <-> PL
FPGA execution/loading
Site electrical behavior
target power
real IC programming
8-Site hardware concurrency
```

## 10. Promotion to Z2

After this milestone passes, keep the Control Station/Manager contract unchanged and replace only the PPU endpoint with a separately qualified real Z2 deployment. If Render -> SWPC passes but Render -> Z2 fails, the investigation space is then concentrated on Z2/ARMv7/PYNQ/network/systemd differences rather than the central Control Station architecture.
