# z2like-demo QEMU ARMv7 Simulation

Status: **Current simulation architecture.** `SWPC` is the single Plasma simulation environment. The canonical PPU backend for `z2like-demo` is one persistent QEMU ARMv7 simulated Z2 running on SWPC. The x86_64 `swpc-z2like` profile remains an engineering surrogate/regression target and is not the `z2like-demo` backend.

## Canonical topology

```text
Simulation Environment: SWPC

SWPC
└── Docker/QEMU ARMv7 simulated Z2
    ├── private Gateway   172.29.33.21:18080
    ├── private Bootstrap 172.29.33.21:18081
    └── canonical ARMv7 PPU Runtime
```

There is no second or third simulation environment. QEMU is a backend inside SWPC.

## Private commissioning / Runtime deployment path

Bootstrap remains on the SWPC-private Docker bridge:

```text
SWPC Local Control Station
  -> local BFF
  -> local mutable Manager registry / Bootstrap credential store
  -> http://172.29.33.21:18081 Bootstrap
  -> verified canonical Z2 PS kit
  -> QEMU ARMv7 PPU Runtime
  -> http://172.29.33.21:18080 Gateway
```

This is where the Console-managed Bootstrap workflow from PR #546 is exercised. Do not expose this Bootstrap endpoint through Render, Cloudflare public routing, or the historical SWPC `:18081` diagnostics hostname.

The simulation verifies kit structure/integrity with `ppu-bootstrap-kit.py`, verifies/stages the canonical PPU release with the current Z2 installer core, and executes the packaged `linux-armv7l` PPU runtime under ARMv7 QEMU. The simulation intentionally uses the pinned QEMU-container Python to execute the PPU runtime; the Plasma Python artifact inside the Z2 kit is integrity-checked as part of the kit but is not installed as the container interpreter.

The QEMU deployment adapter does **not** emulate systemd. Therefore it does not qualify real Z2 service-manager startup, reboot persistence, Unix-socket DAC, or the privileged P3 runtime-activation helper. Activation failure restores the previous simulated Runtime selection, but this is software rollback evidence only.

## Public z2like-demo steady-state path

The public Render service remains a Control Station/Manager, not a Bootstrap proxy:

```text
Browser
  -> Render z2like-demo Console/BFF
  -> Render Manager
  -> HTTPS Cloudflare Access service-token protected managed hostname
  -> Cloudflare Tunnel
  -> SWPC 127.0.0.1:18083
  -> bounded managed Programming ingress
  -> 172.29.33.21:18080 QEMU ARMv7 Gateway
  -> QEMU ARMv7 Plasma Server / configured Mock Sites
```

The Render service uses PPU alias `z2-qemu-ppu`. Its PPU endpoint must remain an HTTPS root URL and the Cloudflare Access client ID/secret remain Render-only transport credentials.

Port ownership on SWPC is deliberately separate:

```text
18080  SWPC x86 surrogate full local Gateway
18081  SWPC x86 surrogate restricted diagnostics/status ingress
18082  SWPC x86 surrogate managed Programming ingress
18083  z2like-demo QEMU ARMv7 managed Programming ingress
```

Inside the private Docker bridge, the simulated Z2 independently owns `172.29.33.21:18080` for Gateway and `172.29.33.21:18081` for Bootstrap. Profile/IP scope prevents those ports from colliding with the host listeners.

The QEMU public ingress does not expose `/api/settings/sites/activation`. The simulation has no real systemd/runtime-activation helper, so exposing that side effect would manufacture a capability that is not present. Programming uses the simulated PPU's canonical initial Mock Site configuration instead.

## SWPC operator flow

Start or verify the persistent simulated Z2:

```bash
cd "$PLASMA_REPO"
python3 scripts/z2like-qemu-sim.py up
python3 scripts/z2like-qemu-sim.py status --write-evidence
```

The device-local Bootstrap token is available only on SWPC when pairing a local Manager:

```bash
python3 scripts/z2like-qemu-sim.py token
```

Do not place that token in repository files, Render environment variables, screenshots, CI artifacts, or general logs.

A canonical Z2 PS kit can be exercised directly through the private Bootstrap acceptance client:

```bash
python3 scripts/z2like-qemu-bootstrap-smoke.py \
  /path/to/plasma-z2-ps-kit-<release>.tar.gz \
  --sidecar /path/to/plasma-z2-ps-kit-<release>.tar.gz.sha256
```

For the normal product-path acceptance, register `http://172.29.33.21:18080` in the SWPC local Manager and use **EMode -> PPU Sites -> Runtime Deployment** so the Browser/BFF/Manager path owns pairing and deployment admission.

After a Runtime is active and `.work/z2like-qemu-sim/install.json` reports `runtime_active`, install the separate public managed ingress:

```bash
sudo bash scripts/plasmactl-z2like-qemu-managed-ingress install
sudo bash scripts/plasmactl-z2like-qemu-managed-ingress verify
```

Cloudflare Tunnel for the z2like-demo managed PPU hostname must target:

```text
http://127.0.0.1:18083
```

The Cloudflare Access application must require a dedicated Render service token. An unauthenticated request must be denied at the edge before the Render service endpoint is changed.

## CI acceptance

The Z2 PS release workflow builds the canonical Z2 kit, starts this ARMv7 QEMU appliance, uploads the complete kit over the authenticated private Bootstrap API, activates the packaged PPU release, and requires Gateway readiness. This proves the software/package path against ARMv7 userspace rather than only static source contracts.

CI still does not prove a physical PYNQ-Z2.

## Qualification boundary

A successful SWPC/QEMU acceptance supports only:

```text
SWPC simulation environment
+ QEMU ARMv7 userspace
+ Bootstrap identity/token/upload/deployment API
+ canonical Z2 PS kit integrity
+ canonical PPU release verification/staging
+ ARMv7 Plasma Server/Gateway execution
+ configured Mock Site programming path
+ software activation rollback
```

It does **not** qualify:

```text
PYNQ-Z2 hardware
real Z2 systemd/reboot persistence
real privileged runtime-activation helper / Unix-socket DAC
PS <-> PL
FPGA bitstream/execution
Site electrical behavior
target power
OpenOCD physical transport
real IC erase/program/verify
physical multi-Site concurrency
```

The required claim remains:

**Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED.**
