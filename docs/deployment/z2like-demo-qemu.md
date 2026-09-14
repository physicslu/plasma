# SWPC z2like-demo QEMU ARMv7 Backend

Status: **simulation software path only**. This document does not qualify a physical PYNQ-Z2.

## Canonical ownership

Plasma has one simulation environment:

```text
Simulation Environment
└── SWPC
    ├── z2like-demo
    │   └── QEMU ARMv7 simulated Z2   <- canonical public-demo PPU backend
    └── swpc-z2like                   <- engineering surrogate only
```

`z2like-demo` has exactly one backend. It does not switch between the x86_64 `swpc-z2like` surrogate and QEMU.

## Product-path topology

The public `z2like-demo` hostname terminates only on a dedicated Control Station Console/BFF running on SWPC:

```text
Browser
  -> z2like-demo public hostname
  -> Cloudflare Access/Tunnel
  -> SWPC 127.0.0.1:18390  z2like-demo Console/BFF
  -> SWPC 127.0.0.1:18380  z2like-demo Manager
  -> private Docker bridge
  -> QEMU ARMv7 simulated Z2
       :18081 independent Bootstrap
       :18080 Plasma Gateway
       :9900  Plasma Server
```

The QEMU container publishes **no host ports**. Manager reaches its fixed private Docker-bridge IPv4 directly. This lets the merged Bootstrap policy derive `http://<QEMU-IP>:18081` from the registered `http://<QEMU-IP>:18080` Gateway endpoint while keeping Bootstrap on the controlled private HTTP commissioning link.

The public Cloudflare hostname must route only to `http://127.0.0.1:18390`. Never expose QEMU `:18080`, QEMU `:18081`, or host `:18080` directly to the Internet.

## Relationship to existing SWPC services

Existing SWPC `swpc-z2like` ports remain unchanged:

```text
127.0.0.1:18080  x86_64 engineering-surrogate full Gateway
127.0.0.1:18081  x86_64 restricted diagnostics/status ingress
127.0.0.1:18082  x86_64 managed Programming ingress
```

They are not the `z2like-demo` backend. In particular, do not widen or repurpose host `18081` for Bootstrap.

The normal SWPC Local Control Station remains on `18190/18280`; the z2like-demo scenario uses its own `18390/18380` Console/Manager pair so the engineering Control Station is not silently retargeted when the public demo is activated. Both pairs reuse the same qualified Control Station release rather than maintaining a second UI/control-plane implementation.

## Start the canonical QEMU target

Prerequisites:

- SWPC Linux with Docker;
- current Plasma repository at a clean committed revision;
- current `local-control-station` release deployed, including `plasma_manager.bootstrap_server`;
- Cloudflare hostname/routing configured externally when public access is required.

Start QEMU and the dedicated Control Station:

```bash
cd "$PLASMA_REPO"
python3 scripts/z2like-demo-qemu.py activate
```

Defaults:

```text
Docker network       plasma-z2like-demo
Private subnet       172.30.77.0/24
QEMU PPU IPv4        172.30.77.2
PPU alias            z2like-qemu
QEMU Gateway         http://172.30.77.2:18080
QEMU Bootstrap       http://172.30.77.2:18081
Demo Manager         http://127.0.0.1:18380
Demo Console         http://127.0.0.1:18390
```

Subnet, QEMU IPv4 and alias can be overridden explicitly with command-line options or the documented `PLASMA_Z2LIKE_DEMO_*` environment variables. Existing conflicting Docker topology fails closed; the script does not silently replace it.

Read-only verification:

```bash
python3 scripts/z2like-demo-qemu.py verify
python3 scripts/z2like-demo-qemu.py status
```

To retrieve the device-local pairing token for the explicit Console pairing step:

```bash
python3 scripts/z2like-demo-qemu.py token
```

That command deliberately exposes a secret to the terminal. Do not put the token in repository files, screenshots, CI artifacts or general logs.

Stop without deleting persistent state:

```bash
python3 scripts/z2like-demo-qemu.py down
```

Persistent Docker volumes, Manager registry, pairing credentials and service units remain intact. This is a stop operation, not a factory reset.

## Bootstrap deployment path

Before a Product Runtime is installed, the QEMU target remains manageable through Bootstrap:

```text
Console Runtime Deployment
  -> BFF
  -> z2like-demo Manager
  -> QEMU Bootstrap :18081
  -> authenticated chunked Z2 PS kit upload
  -> canonical kit SHA-256 verification
  -> kit-local ppu-bootstrap-deployment.py
  -> kit-local retained Z2 installer core
  -> QEMU userspace activation adapter
  -> packaged ARMv7 Plasma Server/Gateway
```

The simulation uses the QEMU container's ARMv7 Python 3.12 interpreter to execute the packaged Runtime. It verifies the kit's Plasma Python artifact and sidecar for integrity but intentionally does **not** install or execute that artifact. Therefore the simulation does not qualify the real `z2-ps` Plasma-owned Python installation contract.

The QEMU userspace supervisor watches `/opt/plasma/current`. A deployment activation failure does not kill Bootstrap: the failed release is left unstarted while the shared deployment transaction reaches its health deadline, restores the previous symlink/configuration, and then the supervisor resumes the restored release. This permits deterministic software rollback testing without pretending to test physical Z2 systemd behavior.

## What this simulation can qualify

When the exact end-to-end scenario passes, evidence may support:

```text
SWPC/QEMU ARMv7 z2like-demo software path
+ Control Station/BFF
+ Manager Bootstrap policy/lifecycle gates
+ device pairing
+ authenticated chunk upload
+ canonical Z2 kit format/integrity
+ kit-local durable deployment coordinator
+ ARMv7 packaged PPU Runtime
+ Gateway/Server readiness
+ software activation rollback/recovery semantics
```

## What it cannot qualify

It does not prove:

- physical PYNQ-Z2 hardware behavior;
- PYNQ/System-Python isolation on a real board;
- Plasma-owned Python installation on a real board;
- real systemd/DAC/socket ownership;
- real Z2 reboot persistence;
- Ethernet behavior of the physical board;
- PS-to-PL or FPGA execution;
- Site electrical I/O or target power;
- real IC erase/program/verify;
- physical multi-Site concurrency.

The qualification statement remains:

> **Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED.**

## Public hostname boundary

Repository code intentionally does not invent or own the external DNS hostname. The operator-managed `z2like-demo` Cloudflare hostname must terminate on `127.0.0.1:18390` only. Cloudflare DNS/Tunnel/Access configuration is external deployment state and requires separate verification on SWPC; repository CI cannot prove it.
