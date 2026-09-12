# `plasmactl` Deployment Profiles

## Status

**Current deployment control-plane contract.**

`plasmactl` is the operator entry point for Plasma deployment/runtime lifecycle commands. A deployment **profile** selects a host role and its backend; it does not collapse development-host, Control Station, surrogate-PPU, and real-appliance ownership into one implementation.

Current profiles:

| Profile | Purpose | Service ownership | Release model | Hardware claim |
|---|---|---|---|---|
| `integration` | SWPC development/integration host | user systemd | repository/runtime environment | none |
| `local-control-station` | Linux reference Control Station: Console/BFF + Manager | user systemd | immutable user-local release | none |
| `swpc-z2like` | x86_64 PS-only PPU surrogate | system systemd | immutable `/opt/plasma/releases/<release-id>` | PS-surrogate software only |
| `z2-ps` | Real PYNQ-Z2 ARMv7 PS-only PPU | system systemd | GitHub-built Python runtime + immutable PPU release | PS runtime/local diagnostic only |

`z2-full` remains future work and requires PS + PL + Site/Programming qualification. The shorthand `z2` remains unavailable until that full boundary is qualified. Neither is an alias of `swpc-z2like`.

## First-principles ownership

The CLI answers:

> Which deployment role is the operator managing?

The backend answers:

> How is that role provisioned, activated, observed and verified safely?

Therefore:

```text
plasmactl
├── integration
│   └── scripts/plasmactl-integration
├── local-control-station
│   └── scripts/plasmactl-local-control-station
├── swpc-z2like
│   └── scripts/plasmactl-swpc-z2like
│       └── scripts/swpc-z2like-ppu-install.sh
└── z2-ps
    └── scripts/plasmactl-z2-ps
        ├── scripts/z2-python-runtime.py
        ├── scripts/ppu-z2-installer.py
        └── scripts/ppu-z2-installer-core.py
```

The local Control Station backend owns only Console/BFF + Manager lifecycle. It never starts a local Plasma Server or Plasma Gateway.

The SWPC backend remains a surrogate-only host adapter. The Z2 backend is distinct: it accepts only a real ARMv7 target at runtime and reuses the canonical PPU release plus the existing Z2 installer instead of reimplementing those internals. The Z2 installer bootstrap is intentionally a two-file unit: the P3 wrapper `ppu-z2-installer.py` requires its sibling `ppu-z2-installer-core.py`.

## Backward compatibility

The pre-profile commands remain integration-host commands by default:

```bash
plasmactl install
plasmactl deploy
plasmactl status
```

They are equivalent to:

```bash
plasmactl install integration
plasmactl deploy integration
plasmactl status integration
```

`update-and-restart` remains an alias of `deploy integration`.

The following remain integration-only:

```text
update
test
restart
web-restart
start
stop
ports
logs
```

There is deliberately no implicit fallback from an unknown profile to `integration`.

## Local Control Station operator flow

The Linux reference profile is documented in detail at `docs/deployment/local-control-station.md`.

### First install

```bash
./scripts/plasmactl install local-control-station \
  --ppu-alias swpc-ppu \
  --ppu-endpoint http://127.0.0.1:18080
```

The PPU endpoint is mandatory on first install and is deployment configuration, not Browser-owned state. HTTP and HTTPS **full Plasma Gateway roots** are accepted; credentials, query strings, fragments and nested paths are rejected. For the co-resident SWPC Z2-like surrogate, `127.0.0.1:18080` is the managed-control Gateway. The `127.0.0.1:18081` listener is intentionally restricted to diagnostics/status and is not a valid Control Station endpoint for Site Desired writes or runtime activation.

Default local bindings:

```text
Console/BFF  127.0.0.1:18190
Manager      127.0.0.1:18280
```

The profile is loopback-only and creates no public listener or firewall rule.

It builds an immutable user-local release under:

```text
~/.local/share/plasma/local-control-station/releases/<git-sha-prefix>
```

and points:

```text
~/.local/share/plasma/local-control-station/current
```

at the active release.

### Deploy a committed source revision

```bash
./scripts/plasmactl deploy local-control-station
```

Like `swpc-z2like`, this profile activates the repository's current **clean committed HEAD** and does not mutate Git history or fetch/merge source. Source acquisition and runtime activation remain separate responsibilities.

Deployment updates the local Manager target, switches the immutable release, restarts only:

```text
plasma-local-manager.service
plasma-control-station.service
```

and verifies the local Console + Manager runtime. A failed activation restores the previous release, profile configuration, Manager configuration, evidence and user units.

Target PPU availability is probed but is deliberately not part of Control Station deployment qualification:

```text
Control Station readiness != PPU readiness != Programming readiness
```

A temporarily unreachable PPU remains non-fatal. If the configured PPU is reachable but `/api/settings/sites` is unavailable, verification fails closed because that proves the endpoint is not the managed-control Gateway surface.

### Verification

```bash
./scripts/plasmactl verify local-control-station
```

This verifies the local runtime/evidence contract, managed-mode BFF wiring, local Manager liveness and local Console health. For a reachable PPU, it also verifies that the configured endpoint exposes the managed Site settings surface instead of only a restricted diagnostics/status surface. It does not qualify PPU execution, Z2, PL, Sites, or real IC programming.

### Cross-platform boundary

`local-control-station` is currently the **Linux user-systemd reference deployment**. macOS and Windows package the same Control Station product/runtime contract through platform-native installation/service mechanisms rather than duplicate Programming or Manager functionality.

## SWPC Z2-like operator flow

### First install

```bash
sudo ./scripts/plasmactl install swpc-z2like
```

Defaults:

```text
PPU ID             swpc-z2like-01
Facility           lab
Restricted ingress 127.0.0.1:18081
Plasma Python      reuse qualified evidence, or auto-select exactly one
                   /opt/plasma/python/*/bin/python3
```

Operator overrides are explicit:

```bash
sudo ./scripts/plasmactl install swpc-z2like \
  --plasma-python /opt/plasma/python/3.12.13/bin/python3 \
  --ppu-id swpc-z2like-01 \
  --facility-id lab \
  --proxy-port 18081
```

If zero or multiple Plasma-owned Python runtimes are available and no already-qualified evidence resolves the interpreter, installation fails closed rather than guessing.

A first install is accepted only when no prior SWPC Z2-like install evidence or appliance-owned `/opt/plasma/current`, `/etc/plasma/ppu.yaml`, system units, or restricted Nginx configuration already exists. This prevents a missing evidence file from being interpreted as permission to overwrite an unknown installation.

If first-install activation fails after that clean boundary is proven, the profile stops/removes only artifacts created inside that prechecked boundary and removes the unqualified target release. Persistent state/log directories are not treated as qualification evidence and are not used to claim installation success.

The SWPC surrogate uses the same P3 privilege boundary as the Z2 PS runtime: Plasma Server owns the authoritative local quiesce socket, Plasma Gateway can reach only the bounded activation-helper socket, and `plasma-runtime-activation.service` can restart exactly `plasma-server.service`. The surrogate remains x86_64 software evidence only.

### Deploy an updated committed source revision

```bash
sudo ./scripts/plasmactl deploy swpc-z2like
```

The privileged SWPC profile does **not** fetch or merge Git. It activates the repository's current **clean committed HEAD**. Source control update and privileged host activation are separate responsibilities.

Before any mutation, deployment requires the install evidence, `/opt/plasma/current`, PPU configuration, system units, and restricted Nginx ownership to agree. An evidence/current-release mismatch fails closed. An existing canonical `/etc/plasma/ppu.yaml` is preserved across the upgrade; deployment must not regenerate `sites: []` over saved Desired state.

Deployment behavior:

```text
validate existing Plasma-owned installation
        |
        v
prove evidence <-> /opt/plasma/current ownership consistency
        |
        v
compare current Git SHA with install evidence
        |
        +-- same SHA -> verify only / idempotent no-op
        |
        v
remove only an inactive, unqualified target from a prior failed retry
        |
        v
snapshot active symlink + owned config/unit/evidence
        |
        v
stop only Plasma system PPU services
        |
        v
temporarily withdraw only Plasma-owned restricted Nginx config
        |
        v
run hardened SWPC Z2-like installer
        |
        v
preserve canonical Site Desired + install P3 helper/quiesce wiring
        |
        v
verify readiness + local Site Desired + bounded activation helper
        |
        v
verify restricted public boundary + local PS loopback
        |
        +-- PASS -> keep new activation
        |
        +-- FAIL -> restore previous activation/config/evidence,
                    remove unqualified target release, restart old activation
```

The backend never implicitly stops integration-host **user** systemd services. Port/service ownership conflicts remain fail-closed; the operator must resolve a conflicting integration runtime explicitly.

### Verification

```bash
sudo ./scripts/plasmactl verify swpc-z2like
```

This is a local, read-only qualification check of the already installed surrogate. It verifies install evidence/current identity, Plasma-owned canonical config, Server/Gateway/runtime-activation system units, active services, direct local Site Desired API, local/restricted health, negative-route isolation, and PS diagnostic loopback. Dynamic canonical Site configuration is accepted within the one-based `id` and `max_supported_sites <= 8` contract.

The public restricted ingress remains intentionally diagnostics/status-only in this profile revision: `/api/settings/sites` is still expected to return `404` there. Expanding the public `z2like-demo` managed-control surface is a separate architecture/security transaction.

It does **not** prove the Render/Manager managed path, ARMv7/PYNQ behavior, PL/FPGA, Site electrical behavior, or real IC programming.

### Status

```bash
./scripts/plasmactl status swpc-z2like
```

Status reports installed evidence and service state, including bounded runtime-activation capability; it does not manufacture a PASS claim.

## Real Z2 PS operator flow

The full package and qualification contract is documented at `docs/deployment/z2-ps-installer.md`.

### GitHub release candidate

`.github/workflows/z2-ps-release.yml` builds a source-tree-independent candidate kit containing:

```text
Plasma-owned CPython ARMv7 runtime
canonical ppu/linux/armv7l release
plasmactl router + z2-ps backend
Z2 PPU installer wrapper + sibling installer core
hash/evidence metadata
```

The canonical PPU release carries the Server/Gateway runtime plus the bounded P3 runtime-activation helper wiring. The helper is not a general privileged command surface: it is limited to controlled restart of `plasma-server.service` after Server-authoritative quiesce.

The CPython build runs in an Ubuntu 22.04 ARMv7 userspace and uses a pinned official Python source archive SHA-256. This removes target-local compilation from the normal clean-Z2 deployment flow.

CI validates the package and ARMv7 userspace behavior, but it is only **software/package qualification**. It cannot prove a physical PYNQ-Z2 runtime.

### First install on clean PYNQ-Z2

After transferring and extracting the GitHub artifact:

```bash
sudo bash scripts/plasmactl install z2-ps \
  --python-artifact artifacts/plasma-python-3.12.13-linux-armv7l.tar.gz \
  --python-sidecar artifacts/plasma-python-3.12.13-linux-armv7l.tar.gz.sha256 \
  --release-artifact artifacts/plasma-ppu-<release-id>-linux-armv7l.tar.gz \
  --release-sidecar artifacts/plasma-ppu-<release-id>-linux-armv7l.tar.gz.sha256 \
  --gateway-host 192.168.2.99 \
  --ppu-id z2-dev-01 \
  --facility-id lab
```

The order is intentional:

```text
verify Python artifact
  -> install /opt/plasma/python/<version>
  -> execute/import-probe it on real ARMv7
  -> verify PPU artifact + installer wrapper/core pair
  -> activate immutable PPU release
  -> start Server + Gateway; Gateway pulls the bounded runtime-activation helper
  -> local health
  -> local PS diagnostic loopback
```

The profile never replaces `/usr/bin/python3` or the PYNQ Python environment.

### Deploy a later PPU release

```bash
sudo bash scripts/plasmactl deploy z2-ps \
  --release-artifact artifacts/plasma-ppu-<new-release-id>-linux-armv7l.tar.gz \
  --release-sidecar artifacts/plasma-ppu-<new-release-id>-linux-armv7l.tar.gz.sha256 \
  --gateway-host 192.168.2.99 \
  --ppu-id z2-dev-01 \
  --facility-id lab
```

When no new Python artifact/path is provided, `deploy z2-ps` reuses `/opt/plasma/install/python-runtime.json` rather than guessing among interpreters.

### Verification

```bash
bash scripts/plasmactl verify z2-ps
```

A PASS requires a real Linux ARMv7 runtime, active Plasma Server/Gateway, Gateway readiness and a local PS diagnostic loopback with `endpoint=ps` / `source=ps`. P3 additionally requires the bounded runtime-activation helper to be installed with the packaged service ownership/DAC contract; CI can prove packaging and software contracts, while the real Z2 must prove the actual systemd and Unix-socket permissions.

This qualifies only:

```text
Real PYNQ-Z2 / ARMv7 PS software runtime
local Z2 Gateway -> Server -> PS diagnostic path
```

It does **not** qualify:

```text
PS <-> PL
FPGA bitstream/execution
Site electrical path
target power
real IC erase/program/verify
8-Site hardware concurrency
production programmer readiness
```

After local verification, the Control Station uses its existing Manager registry workflow:

```text
Add PPU
-> alias + http://<Z2-IP>:18080
-> Manager observation
-> Validate & Enable
-> Managed PS Loopback
```

Managed PS Loopback is a separate end-to-end acceptance layer and must be retained for the exact deployed identities.

### Status

```bash
bash scripts/plasmactl status z2-ps
```

Status reports release ID, source SHA, isolated Plasma Python path, Gateway endpoint and system-service state. It is observational only; `verify z2-ps` is the executable local acceptance command.

## Qualification boundaries

### `swpc-z2like`

```text
x86_64 SWPC
+ Plasma Server/Gateway
+ canonical Site Desired persistence
+ bounded P3 runtime-activation helper/quiesce wiring
+ PS diagnostic behavior
+ production-like filesystem/service ownership
```

This is not Real Z2 qualification. The public restricted ingress remains narrower than the local Gateway capability until separately approved.

### `z2-ps`

```text
Real PYNQ-Z2 / ARMv7
+ isolated Plasma Python
+ canonical PPU release
+ systemd Server/Gateway/bounded runtime-activation helper
+ local PS diagnostic behavior
```

This remains PS-only qualification.

Mock must not be enabled to turn missing PL/Site/IC boundaries green.

## Relationship to `verify fleet`

The existing command remains unchanged:

```bash
plasmactl verify fleet
```

It validates Manager/Fleet observation. It is not a substitute for `verify local-control-station`, `verify swpc-z2like`, `verify z2-ps`, or Managed PS Loopback, and none of these is a substitute for PL/Site/real-IC acceptance.
