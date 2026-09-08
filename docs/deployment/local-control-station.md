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
future macOS package           -> same product/runtime contract
future Windows package         -> same product/runtime contract
```

These are deployment/package variants, not duplicated feature implementations.

## Linux reference ownership

The first implementation is intentionally Linux-only and uses **user systemd**. This is the SWPC reference deployment for future platform packages.

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

The value must identify the Plasma Gateway root. Embedded credentials, query strings, fragments, and nested paths are rejected.

Examples:

```text
SWPC co-resident Z2-like restricted ingress
http://127.0.0.1:18081

Future real Z2 on a trusted local network
http://192.168.10.21:18080
```

The Manager/BFF target alias is fixed by deployment configuration. Browser selection does not rewrite the backend target.

## Install

First install requires an explicit PPU endpoint:

```bash
./scripts/plasmactl install local-control-station \
  --ppu-alias swpc-ppu \
  --ppu-endpoint http://127.0.0.1:18081
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
- Console root responds on loopback.

The configured PPU `/api/health/live` is probed as additional evidence, but an unavailable target is non-fatal for **Control Station deployment qualification**.

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

After the SWPC local-control-station runtime is accepted, the intended role is:

```text
plasma.open4th.com
  -> Cloudflare Tunnel
  -> SWPC 127.0.0.1:18190
  -> Local Control Station Console/BFF
```

The tunnel should point at the loopback Console. The profile itself must not bind the Console publicly or open a firewall port.

## macOS / Windows

`plasmactl local-control-station` is **not** the macOS or Windows installer.

Future platform packages must preserve the same logical runtime contract:

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

## Future real Z2 profiles

Real hardware remains a separate deployment family:

```text
z2-ps      future Real Z2 PS-only qualification
z2-full    future PS + PL + Site/Programming qualification
z2         intentionally unavailable until z2-full is qualified
```

`swpc-z2like` must never be silently aliased to any of these profiles.
