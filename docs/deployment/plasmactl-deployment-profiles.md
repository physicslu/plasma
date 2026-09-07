# `plasmactl` Deployment Profiles

## Status

**Current deployment control-plane contract.**

`plasmactl` is the operator entry point for Plasma deployment/runtime lifecycle commands. A deployment **profile** selects a host role and its backend; it does not collapse development-host and appliance-style ownership into one implementation.

Initial profiles:

| Profile | Purpose | Service ownership | Release model | Hardware claim |
|---|---|---|---|---|
| `integration` | SWPC development/integration host | user systemd | repository/runtime environment | none |
| `swpc-z2like` | x86_64 PS-only PPU surrogate | system systemd | immutable `/opt/plasma/releases/<release-id>` | PS-surrogate software only |

Future `z2-ps` / `z2-full` profiles require their own implementation and qualification. They are not aliases of `swpc-z2like`.

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
└── swpc-z2like
    └── scripts/plasmactl-swpc-z2like
        └── scripts/swpc-z2like-ppu-install.sh
```

The hardened SWPC installer remains the host-mutating implementation. `plasmactl-swpc-z2like` adds lifecycle orchestration, evidence/status checks and upgrade rollback; it does not duplicate the installer internals.

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

## SWPC Z2-like operator flow

### First install

```bash
sudo ./scripts/plasmactl install swpc-z2like
```

Defaults:

```text
PPU ID            swpc-z2like-01
Facility          lab
Restricted ingress 127.0.0.1:18081
Plasma Python     reuse qualified evidence, or auto-select exactly one
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

### Deploy an updated committed source revision

```bash
sudo ./scripts/plasmactl deploy swpc-z2like
```

Unlike `deploy integration`, the privileged SWPC profile does **not** fetch or merge Git. It activates the repository's current **clean committed HEAD**. Source control update and privileged host activation are separate responsibilities.

This prevents a root deployment process from silently acquiring Git credentials or changing repository history.

Deployment behavior:

```text
validate existing Plasma-owned installation
        |
        v
compare current Git SHA with install evidence
        |
        +-- same SHA -> verify only / idempotent no-op
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
        +-- FAIL -> restore previous activation/config/evidence and restart it
```

The backend never implicitly stops integration-host **user** systemd services. Port/service ownership conflicts remain fail-closed; the operator must resolve a conflicting integration runtime explicitly.

A failed deployment may leave an unreferenced immutable release directory for forensic inspection. The active `/opt/plasma/current` and install evidence are rolled back to the previous qualified activation when rollback succeeds.

## Verification

```bash
./scripts/plasmactl verify swpc-z2like
```

This is a local, read-only qualification check of the already installed surrogate. It verifies:

- install evidence contract;
- Plasma-owned immutable activation and system units;
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

It validates Manager/Fleet observation. It is not a substitute for `verify swpc-z2like`, and neither is a substitute for real Z2/PL/Site/IC acceptance.
