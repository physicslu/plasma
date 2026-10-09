# SWPC z2like-demo QEMU ARMv7 Backend

Status: **simulation software path only**. This document does not qualify a physical PYNQ-Z2.

## Canonical ownership

Plasma has one simulation environment:

```text
Simulation Environment
└── SWPC
    ├── z2like-demo
    │   └── QEMU ARMv7 simulated Z2   <- canonical z2like-demo PPU backend
    └── swpc-z2like                   <- engineering surrogate only
```

`z2like-demo` has exactly one PPU backend. It does not switch between the x86_64 `swpc-z2like` surrogate and QEMU.

The public Control Station remains **Render-hosted**. QEMU replaces only the PPU backend.

## Canonical public topology

```text
Browser
  -> https://z2like-demo.open4th.com
  -> Render Control Station Console/BFF
  -> Render Plasma Manager
  -> https://ppu-managed-lab.open4th.com
  -> Cloudflare Access service-token policy + Tunnel
  -> SWPC 127.0.0.1:18082 managed ingress
  -> private Docker bridge
  -> QEMU ARMv7 simulated Z2 172.30.77.2
       :18080 Plasma Gateway
       :18081 independent Bootstrap
       :9900  Plasma Server
```

The QEMU container publishes **no host ports**. SWPC Nginx owns the loopback-only `18082` boundary and forwards only the bounded managed-control allowlist to QEMU `172.30.77.2:18080`.

Do not repoint `z2like-demo.open4th.com` to SWPC. Its DNS/Render ownership is intentional. Do not expose QEMU `:18080` or `:18081` directly to the Internet.

## Active public hostname roles

| Hostname | Ownership | Role |
| --- | --- | --- |
| `plasma-demo.open4th.com` | Render | Public Mock Demo with Render-local Mock PPU |
| `z2like-demo.open4th.com` | Render | Product Control Station whose PPU backend is SWPC QEMU ARMv7 |
| `plasma.open4th.com` | SWPC | Local Control Station: `18190 -> 18280 -> 18080` x86 engineering surrogate |
| `ppu-managed-lab.open4th.com` | SWPC | Cloudflare Access protected managed ingress on host `18082`, owned by z2like-demo QEMU path |

The former `ppu-lab.open4th.com` hostname and its SWPC host `18081` diagnostics ingress were retired by Issue #549. They are not active routing surfaces.

These hostnames are different deployment/security boundaries. A shared port number in another profile does not imply shared ownership.

## Port/profile ownership

### SWPC x86 engineering surrogate

```text
127.0.0.1:18080  x86_64 full Gateway used by plasma.open4th.com path
127.0.0.1:18081  retired; no host diagnostics/public listener
```

### z2like-demo public backend bridge

```text
127.0.0.1:18082       bounded managed ingress for ppu-managed-lab.open4th.com
172.30.77.2:18080      private QEMU Plasma Gateway
172.30.77.2:18081      private QEMU Bootstrap/recovery service
```

The migration of host `18082` from the historical x86 managed ingress to QEMU is explicit. It does not recreate host `18081`, and it does not change the x86 full Gateway used by `plasma.open4th.com`.

### SWPC internal maintenance fixture

```text
127.0.0.1:18380  internal Bootstrap-capable Manager
127.0.0.1:18390  internal acceptance Console/BFF
```

`18380/18390` are not the public z2like-demo Control Station. They exist only for SWPC-local Bootstrap deployment/acceptance and may be removed later if that maintenance function is replaced.

## One-command operator flow

Normal update from a clean local `main`:

```bash
cd "$PLASMA_REPO"
sudo ./scripts/plasmactl update z2like-demo
```

This command:

1. verifies the repository is clean and on `main`;
2. fetches `origin/main` and refuses ahead/diverged history;
3. performs only `git pull --ff-only origin main`;
4. re-executes the newly pulled `plasmactl` code;
5. starts/verifies the private ARMv7 QEMU target;
6. builds a canonical ARMv7 PPU Runtime and simulation Z2 PS kit;
7. deploys through the persistent SWPC-local Bootstrap Manager Platform-maintenance gates without changing programming Registration;
8. migrates/reconciles host `18082` to the QEMU managed ingress;
9. verifies QEMU Gateway execution readiness;
10. verifies the bounded `18082` ingress;
11. verifies the Render public registry and public managed health path.

No manual `git pull`, `curl`, or per-service health-check sequence is required.

Deploy the already checked-out clean committed revision without changing Git:

```bash
sudo ./scripts/plasmactl deploy z2like-demo
```

Read-only verification/status:

```bash
sudo ./scripts/plasmactl verify z2like-demo
sudo ./scripts/plasmactl status z2like-demo
```

Public verification is fail-closed by default. `PLASMA_Z2LIKE_DEMO_SKIP_PUBLIC_VERIFY=1` exists only for isolated engineering work and explicitly does **not** produce public-path qualification.

## Bootstrap deployment behavior

The SWPC-local maintenance Manager is the only component that drives the private QEMU Bootstrap mutation API:

```text
SWPC local operator
  -> internal Manager :18380
  -> QEMU Bootstrap :18081
  -> device pairing if required
  -> authenticated 1 MiB chunk upload
  -> canonical Z2 PS kit verification
  -> kit-local OpenOCD artifact verification/install
  -> kit-local durable deployment coordinator
  -> QEMU userspace activation adapter
  -> packaged ARMv7 Plasma Server/Gateway
```

Platform maintenance remains fail-closed and independent from programming Registration:

- the SWPC-local maintenance Manager uses a **read-only config connection registry** with `registry_state_path: null`; it does not own or mutate Programming Registration lifecycle;
- the public production control plane remains the sole owner of Programming Registration admission;
- a legacy SWPC-local `manager-registry.json` may remain on disk after upgrade, but it is ignored and is not an authority once the config-only maintenance registry is active;
- device-bound Bootstrap pairing is required for authenticated mutation;
- active Site execution blocks Platform mutation;
- a `runtime_absent` target may receive first Runtime deployment without a Runtime-idle observation;
- an existing `runtime_active` target requires a newer current trusted idle Manager observation after target restart;
- recovery/unknown Runtime state is rejected.

The device-local pairing token is read only from the local QEMU container when pairing is required and is never printed by the one-command deployment path.

OpenOCD is part of the canonical kit deployment contract. CI and live deployment must not preinstall or copy an OpenOCD runtime into the target as an out-of-band prerequisite; qualification smoke runs only after kit deployment and reads the installed `/opt/plasma/install/openocd-runtime.json` evidence.

## Managed-ingress security boundary

`ppu-managed-lab.open4th.com` continues to require the existing Cloudflare Access service identity owned by the Render deployment. Repository code does not create or weaken that external policy.

The host `18082` Nginx ingress remains loopback-only and allowlisted. It permits the managed product surfaces required for observation, Site Desired, bounded Runtime Activation, Mock programming Jobs/Batches and diagnostics while excluding generic API proxying, Gateway-setting mutation and PPU-network mutation/activation.

Cloudflare Access is transport identity only. Plasma Gateway remains the final application authorization, Site scope, idempotency and execution authority.

## `ppu-lab` retirement boundary

Issue #549 retired the former `ppu-lab.open4th.com` route and SWPC host `127.0.0.1:18081` diagnostics/status/PS-loopback listener. Current repository contracts must not recreate either surface.

QEMU `172.30.77.2:18081` and real-Z2 `<Z2-IP>:18081` are separate Bootstrap/recovery ports and are **not** part of that retirement.

## What this simulation can qualify

When the exact end-to-end scenario passes, evidence may support:

```text
SWPC/QEMU ARMv7 z2like-demo software path
+ Render Control Station/Manager product path
+ Cloudflare-protected bounded managed ingress contract
+ private Bootstrap lifecycle policy
+ device pairing
+ authenticated chunk upload
+ canonical Z2 kit format/integrity
+ kit-local durable deployment coordinator
+ ARMv7 packaged PPU Runtime
+ pinned ARMv7 OpenOCD runtime artifact install/execution
+ OpenOCD version/script/shared-library checks
+ software-only OpenOCD dummy-adapter smoke
+ standalone Control Station Console/BFF -> Manager -> PPU Gateway -> ARMv7 PS -> real OpenOCD Worker -> Tcl RPC
+ fixed safe OpenOCD `version` probe with no Browser-supplied Tcl command surface
+ eight isolated OpenOCD workers with one-Site kill/restart failure isolation
+ Gateway/Server readiness
+ software activation rollback/recovery semantics
```

Repository CI can prove the software composition and QEMU path. Live SWPC, Render and Cloudflare routing remain deployment-state evidence and must be verified at deployment time.

## What it cannot qualify

It does not prove:

- physical PYNQ-Z2 hardware behavior;
- PYNQ/System-Python isolation on a real board;
- Plasma-owned Python installation on a real board;
- real systemd/DAC/socket ownership on Z2;
- real Z2 reboot persistence;
- Ethernet behavior of the physical board;
- live SWPC-host operator qualification unless the SWPC acceptance is run on that host;
- SWD/JTAG through PL or a physical debug adapter;
- PS-to-PL or FPGA execution;
- Site electrical I/O or target power;
- real IC erase/program/verify;
- physical multi-Site concurrency.

OpenOCD evidence in this simulation remains explicitly software-only:

```text
ARMv7 OpenOCD binary/package/install/dummy-adapter smoke = QUALIFIED in CI QEMU
Console/BFF -> Manager -> Gateway -> Worker -> Tcl RPC     = QUALIFIED in CI QEMU
8-Site worker isolation + one-Site kill/restart            = QUALIFIED in CI QEMU
live SWPC operator-run control-plane qualification         = PENDING until main-only Browser Runtime live artifact PASS
SWD/JTAG / PL / target / real IC                          = NOT QUALIFIED
hardware_runtime_ready                                    = false
```

The main-only Browser Runtime live gate is the closure gate for the OpenOCD control-plane milestone. After canonical kit deployment and return to `commissioned`, it drives the public Console/BFF managed OpenOCD diagnostic across Sites 1–8 and then executes the exact-commit ARMv7 QEMU 8-worker isolation acceptance, including Site 5 kill, seven surviving workers and Site 5 restart. A PASS remains software/control-plane evidence only and must retain `hardware_runtime_ready=false`.

The qualification statement remains:

> **Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED.**
