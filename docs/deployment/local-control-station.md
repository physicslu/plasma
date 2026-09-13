# Local Control Station Reference Deployment

## Status

`local-control-station` is the Linux reference deployment for the Plasma **upper computer / Control Station** role.

It deploys the same Control Station product code used by the managed Render lane. It is not a second implementation of Programming workflows or APIs.

```text
Browser
  |
  v
Control Station Console/BFF  127.0.0.1:18190
  |
  v
Plasma Manager               127.0.0.1:18280
  |
  v
Configured PPU Plasma Gateway endpoint
```

The profile deliberately does **not** start:

```text
Plasma Server
Plasma Gateway
Mock Provider
FPGA/PL runtime
```

The PPU is a separate deployment role.

## Why this profile exists

Plasma needs one Control Station codebase that can be exercised in several environments:

```text
Render demo                    -> same product code + Mock lane
Render z2like demo             -> same product code + Manager -> SWPC PPU
Linux local-control-station    -> same product code + local Manager -> configured PPU
macOS package pilot            -> same product/runtime contract
Windows package pilot          -> same product/runtime contract
```

These are deployment/package variants, not duplicated feature implementations.

## Linux reference ownership

The Linux reference implementation uses **user systemd**. Platform packages use their native service managers while preserving the same product contract.

Runtime state is separated from the Git worktree:

```text
~/.config/plasma/local-control-station/
  profile.env
  manager.yaml

~/.local/state/plasma/local-control-station/
  install.json
  manager-observations.sqlite3

~/.local/share/plasma/local-control-station/
  current -> releases/<git-sha-prefix>
  releases/<git-sha-prefix>/
    venv/
    web/
```

User units:

```text
plasma-local-manager.service
plasma-control-station.service
```

The Console and Manager bind to loopback only. Public/LAN exposure is not created by this profile.

## PPU target contract

The target is configured explicitly and is not hard-coded to SWPC or PYNQ-Z2.

Accepted endpoint form:

```text
http://HOST[:PORT]
https://HOST[:PORT]
```

The value must identify the **full Plasma Gateway root used for managed control**, not a narrower diagnostics/status proxy. Embedded credentials, query strings, fragments, and nested paths are rejected.

Examples:

```text
SWPC co-resident Z2-like full local Gateway
http://127.0.0.1:18080

Real Z2 on a trusted local network
http://192.168.10.21:18080
```

The SWPC Z2-like `127.0.0.1:18081` listener is intentionally a restricted diagnostics/status ingress. It does not expose Site Desired writes or runtime activation and **must not** be configured as the local Control Station PPU endpoint.

The Manager/BFF target alias is fixed by deployment configuration. Browser selection does not rewrite the backend target.

## Install

First install requires an explicit PPU endpoint:

```bash
./scripts/plasmactl install local-control-station \
  --ppu-alias swpc-ppu \
  --ppu-endpoint http://127.0.0.1:18080
```

Optional overrides:

```text
--python PATH
--ppu-alias ALIAS
--ppu-endpoint URL
--console-port PORT
--manager-port PORT
```

Default local ports:

```text
Console/BFF  127.0.0.1:18190
Manager      127.0.0.1:18280
```

These are intentional `local-control-station` profile defaults, not replacements for the generic/package Manager default `18180`. See `docs/deployment/port-profile-matrix.md` for the canonical cross-profile map.

`install` builds an immutable release, writes profile configuration and user-systemd units, and enables the units. It does not start them.

## Deploy

```bash
./scripts/plasmactl deploy local-control-station
```

The profile activates the repository's **current clean committed HEAD**. It does not run `git pull`, merge, checkout, reset, or other source-control mutation.

Deployment flow:

```text
clean committed source
        |
        v
build/reuse immutable release
        |
        v
write Manager target + Console/BFF units
        |
        v
switch current release
        |
        v
restart local Manager
        |
        v
restart Console/BFF
        |
        v
local runtime verification
        |
        +-- PASS -> keep activation
        |
        +-- FAIL -> restore previous release/config/units
```

An unreachable PPU does **not** invalidate the Control Station deployment itself. PPU reachability is reported separately because:

```text
Control Station readiness != PPU readiness != Programming readiness
```

However, if the configured PPU is reachable and `/api/health/live` succeeds while `/api/settings/sites` is unavailable, verification fails closed. That condition proves the configured endpoint is not the managed-control Gateway surface, which is a deployment configuration error rather than temporary PPU unavailability.

## Verification

```bash
./scripts/plasmactl verify local-control-station
```

This verifies:

- install evidence and active immutable release agree;
- both user-systemd units are Plasma-owned and active;
- Console is in managed mode;
- Console BFF points to the local Manager;
- fixed PPU alias is injected into the BFF;
- Manager liveness passes on loopback;
- Console root responds on loopback;
- a reachable configured PPU exposes the managed Site configuration surface rather than only a restricted diagnostics/status surface.

The configured PPU `/api/health/live` is probed as additional evidence. An unreachable target remains non-fatal for **Control Station deployment qualification**, but a reachable target with an incompatible managed-control surface fails configuration verification.

It does not prove:

```text
PPU execution readiness
PYNQ-Z2 / ARM qualification
PS <-> PL integration
FPGA behavior
Site electrical behavior
real IC erase/program/verify
8-Site hardware concurrency
```

Those are separate target/hardware acceptance layers.

## `plasma.open4th.com` role

When the SWPC local-control-station runtime is intentionally exposed through the existing tunnel, the routing role is:

```text
plasma.open4th.com
  -> Cloudflare Tunnel
  -> SWPC 127.0.0.1:18190
  -> Local Control Station Console/BFF
```

The tunnel should point at the loopback Console. The profile itself must not bind the Console publicly or open a firewall port.

## macOS / Windows

`plasmactl local-control-station` is **not** the macOS or Windows installer.

The existing macOS/Windows package pilots preserve the same logical runtime contract:

```text
Control Station Console/BFF
        |
        v
Manager
        |
        v
PPU API
```

Only packaging/service integration changes by OS. Product features, Programming workflows, Manager contract, and PPU API remain shared.

## Real Z2 qualification profiles

Real hardware is a separate deployment family:

```text
z2-ps      implemented Real Z2 PS-only deployment/qualification profile
z2-full    future PS + PL + Site/Programming qualification
z2         intentionally unavailable until z2-full is qualified
```

`z2-ps` being implemented does not mean the current revision is qualified on a real board; real-board install/readiness/PS-loopback evidence remains a separate acceptance step. `swpc-z2like` must never be silently aliased to any Real Z2 profile.
