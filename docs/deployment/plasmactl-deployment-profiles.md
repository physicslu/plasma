# `plasmactl` Deployment Profiles

## Status

**Current deployment control-plane contract.**

`plasmactl` is the operator entry point for Plasma deployment/runtime lifecycle commands. A deployment **profile** selects a host role and its backend; it does not collapse development-host, Control Station, and appliance-style ownership into one implementation.

Current profiles:

| Profile | Purpose | Service ownership | Release model | Hardware claim |
|---|---|---|---|---|
| `integration` | SWPC development/integration host | user systemd | repository/runtime environment | none |
| `local-control-station` | Linux reference Control Station: Console/BFF + Manager | user systemd | immutable user-local release | none |
| `swpc-z2like` | x86_64 PS-only PPU surrogate | system systemd | immutable `/opt/plasma/releases/<release-id>` | PS-surrogate software only |

Future `z2-ps` / `z2-full` profiles require their own implementation and qualification. They are not aliases of `swpc-z2like`. The shorthand `z2` remains unavailable until the full real-Z2 boundary is qualified.

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
└── swpc-z2like
    └── scripts/plasmactl-swpc-z2like
        └── scripts/swpc-z2like-ppu-install.sh
```

The local Control Station backend owns only Console/BFF + Manager lifecycle. It never starts a local Plasma Server or Plasma Gateway.

The hardened SWPC installer remains the host-mutating implementation for the PPU-surrogate role. `plasmactl-swpc-z2like` adds lifecycle orchestration, evidence/status checks and activation rollback; it does not duplicate the installer internals.

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

The following remain integration-only in this phase:

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
  --ppu-endpoint http://127.0.0.1:18081
```

The PPU endpoint is mandatory on first install and is deployment configuration, not Browser-owned state. HTTP and HTTPS Gateway roots are accepted; credentials, query strings, fragments and nested paths are rejected.

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

### Verification

```bash
./scripts/plasmactl verify local-control-station
```

This verifies the local runtime/evidence contract, managed-mode BFF wiring, local Manager liveness and local Console health. It does not qualify PPU execution, Z2, PL, Sites, or real IC programming.

### Cross-platform boundary

`local-control-station` is currently the **Linux user-systemd reference deployment**. macOS and Windows are expected to package the same Control Station product/runtime contract through platform-native installation/service mechanisms rather than duplicate Programming or Manager functionality.

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

### Deploy an updated committed source revision

```bash
sudo ./scripts/plasmactl deploy swpc-z2like
```

Unlike `deploy integration`, the privileged SWPC profile does **not** fetch or merge Git. It activates the repository's current **clean committed HEAD**. Source control update and privileged host activation are separate responsibilities.

This prevents a root deployment process from silently acquiring Git credentials or changing repository history.

Before any mutation, deployment requires the install evidence, `/opt/plasma/current`, PPU configuration, system units, and restricted Nginx ownership to agree. An evidence/current-release mismatch fails closed.

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
verify readiness + restricted boundary + local PS loopback
        |
        +-- PASS -> keep new activation
        |
        +-- FAIL -> restore previous activation/config/evidence,
                    remove unqualified target release, restart old activation
```

The backend never implicitly stops integration-host **user** systemd services. Port/service ownership conflicts remain fail-closed; the operator must resolve a conflicting integration runtime explicitly.

A failed upgrade is designed to leave the previous qualified release active and to remove the failed target release after rollback, so retrying the same clean committed SHA does not collide with an unqualified immutable-release directory. If rollback itself is incomplete, the command returns a critical failure and does not claim qualification.

## Verification

```bash
./scripts/plasmactl verify swpc-z2like
```

This is a local, read-only qualification check of the already installed surrogate. It verifies:

- install evidence contract;
- install evidence and active immutable release identity agree;
- Plasma-owned PPU configuration, system units and restricted Nginx ownership;
- `plasma-server.service` and `plasma-web.service` active;
- direct local Gateway readiness on `127.0.0.1:18080`;
- restricted ingress readiness on `127.0.0.1:18081`;
- `/api/settings/sites` remains HTTP 404 on restricted ingress;
- PS diagnostic loopback returns from the PS endpoint with matching CRC/payload.

It does **not** prove the Render/Manager managed path. Managed Control Station -> BFF -> Manager -> SWPC acceptance remains the separate runtime-acceptance layer documented by the managed PS qualification flow.

## Status

```bash
./scripts/plasmactl status swpc-z2like
```

Status reports installed evidence such as release ID, Git SHA, architecture, Plasma Python, private Gateway/restricted ingress, Site count, active release and system-service state.

Status does not manufacture a PASS claim. `verify` is the executable local acceptance command.

## Qualification boundary

`swpc-z2like` means:

```text
x86_64 SWPC
  + Plasma Server
  + Plasma Gateway
  + PS diagnostic behavior
  + production-like filesystem/service ownership
  + restricted ingress
```

It explicitly does **not** mean:

```text
PYNQ-Z2 / ARMv7 qualified
PS <-> PL qualified
FPGA bitstream qualified
Site electrical path qualified
real IC erase/program/verify qualified
8-Site hardware concurrency qualified
production programmer qualified
```

Mock must not be enabled to turn those missing boundaries green.

## Relationship to `verify fleet`

The existing command remains unchanged:

```bash
plasmactl verify fleet
```

It validates Manager/Fleet observation. It is not a substitute for `verify local-control-station` or `verify swpc-z2like`, and none of these is a substitute for real Z2/PL/Site/IC acceptance.
