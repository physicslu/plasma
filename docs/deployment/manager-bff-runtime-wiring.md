# Plasma Manager BFF Runtime Wiring

## Purpose

The Control Console Manager BFF must be reproducible from checked-in deployment logic. A working deployment must not depend on a shell-exported environment variable, `systemctl import-environment`, or an undocumented systemd drop-in.

This document defines the integration-host wiring for the current narrow Manager Phase-0 PS Loopback relay.

## Source of truth

`plasmactl` deployment schema v5 owns the BFF target selection through:

```text
PLASMA_MANAGER_ENABLED
PLASMA_MANAGER_CONFIG
PLASMA_MANAGER_PPU_ALIAS
```

`PLASMA_MANAGER_CONFIG` remains the source of truth for the Manager bind address, port, and PPU registry. `PLASMA_MANAGER_PPU_ALIAS` selects one already-registered PPU for the fixed Phase-0 BFF command path.

There is intentionally no independent persistent `PLASMA_MANAGER_API_URL` deployment setting. `plasmactl` derives the Web BFF URL from the Manager configuration so the Manager port is not duplicated in two operator-owned configuration surfaces.

## Enabled Manager contract

When `PLASMA_MANAGER_ENABLED=1`, deployment fails closed unless all of the following are true:

1. `PLASMA_MANAGER_CONFIG` exists and parses successfully.
2. `PLASMA_MANAGER_PPU_ALIAS` is non-empty and systemd-safe.
3. The selected alias exactly matches one `ppus[].alias` entry in the Manager registry.
4. The Manager bind is local: loopback or wildcard only for this same-host BFF deployment.

`plasmactl` normalizes wildcard binds to loopback for the BFF connection. For example:

```text
Manager bind 0.0.0.0:18180 -> BFF URL http://127.0.0.1:18180
Manager bind [::]:18180     -> BFF URL http://[::1]:18180
```

An external Manager bind is rejected by this deployment contract rather than silently exposing or routing the BFF to another host.

## Generated Vite service

With Manager enabled, `plasma-vite.service` receives runtime environment owned by `plasmactl`:

```text
Environment=PLASMA_MANAGER_API_URL=<derived loopback Manager URL>
Environment=PLASMA_MANAGER_PPU_ALIAS=<selected registry alias>
```

The Vite unit also declares `plasma-manager.service` in `After=` and `Wants=` so service startup ordering matches the same-host BFF dependency.

`vite.config.ts` then bridges these host-process values into the Vinext/Worker runtime. The BFF route independently keeps its loopback-only URL and alias validation.

## Manager-disabled contract

When `PLASMA_MANAGER_ENABLED=0`:

- Plasma remains a standalone PPU deployment.
- `plasma-manager.service` is not part of the active service set.
- Manager BFF environment is not injected into `plasma-vite.service`.
- Existing PPU-local Gateway and programming execution remain independent of Manager.

## Schema v4 to v5 migration

Schema v5 adds `PLASMA_MANAGER_PPU_ALIAS`.

Migration behavior is intentionally conservative:

- an existing explicit alias is preserved;
- a missing alias is added as an empty value;
- no alias is inferred from the first registry entry;
- Manager-disabled deployments remain valid with an empty alias;
- a Manager-enabled deployment with an empty alias fails closed before runtime activation.

The operator must therefore choose the command-target alias explicitly. This avoids silently changing command ownership when the Manager registry later contains multiple PPUs.

Example for the current SWPC laboratory registry:

```text
PLASMA_MANAGER_ENABLED=1
PLASMA_MANAGER_CONFIG=/home/<user>/.config/plasma/manager.yaml
PLASMA_MANAGER_PPU_ALIAS=ppu-a
```

`ppu-a` is an integration-host example, not a product-wide constant.

## Validation boundary

These deployment checks prove deterministic configuration migration and systemd wiring. They do not prove the production runtime path by themselves.

After merge and explicit deployment approval, SWPC acceptance must still prove:

```text
Control Console
  -> Web BFF
  -> Plasma Manager
  -> PPU REST Gateway
  -> Plasma Server
  -> PS
  -> Plasma Server
  -> PPU REST Gateway
  -> Plasma Manager
  -> Web BFF
  -> Control Console
```

PL and IC remain fail-closed extension points. This wiring change does not implement PS <-> PL, PL <-> IC, FPGA behavior, or real IC programming.
