# Plasma Product Deployment Foundation

> Status: **Plan**. This document defines the approved product deployment direction and the first implemented read-only readiness audit. Install, upgrade, rollback, launchd/systemd activation, release packaging, and Z2 runtime acceptance are not yet implemented by this document alone.

## 1. Purpose

Plasma must stop treating the SWPC integration host as the product runtime topology. SWPC remains useful for development, CI-adjacent integration, staging, and diagnostics, but the product deployment is split into two explicit roles:

```text
Mac Control Station
├── Plasma Control Console
├── Manager BFF runtime
└── Plasma Manager
        |
        | managed network route
        v
Z2 / PPU
├── PPU Gateway
├── Plasma Server
└── PS -> PL -> Site hardware path
```

The first product acceptance path is intentionally narrower than hardware acceptance:

```text
Mac Console/BFF
  -> Manager
  -> Z2 Gateway
  -> Z2 Plasma Server
  -> Z2 PS diagnostic handler
  -> return
```

A passing managed PS Loopback proves the deployed software node and managed route. It does not prove PS <-> PL, FPGA execution, Site electrical behavior, or real IC programming.

## 2. Deployment roles

### 2.1 Control Station

The Control Station is a macOS operator/fleet node. It owns:

- Plasma Control Console;
- same-host Manager BFF runtime;
- Plasma Manager;
- PPU registry and fleet-level routing configuration;
- operator-facing logs and effective-version observability.

It does **not** own PPU Site execution, FPGA behavior, target power, or real IC programming.

The v1 service-management baseline is per-user macOS `launchd` **LaunchAgents**. Product service activation must not depend on Linux `systemd` commands.

The intended user-local persistence roots are:

```text
~/Library/Application Support/Plasma/
├── releases/
├── current -> releases/<version>/
├── config/
└── state/

~/Library/Logs/Plasma/
```

Exact installer mechanics remain to be implemented and validated before these paths become Current deployment behavior.

### 2.2 PPU

The PPU is an embedded Linux execution appliance. The current hardware development target is PYNQ-Z2.

The PPU owns:

- Plasma Web REST Gateway;
- Plasma Server;
- PPU identity and Site topology/capability;
- local Job/Batch execution;
- PS/PL and target-interface execution when those hardware layers are enabled and validated.

The PPU does **not** host the Control Console, Manager, Vite development server, Node.js, or npm in the product baseline.

The v1 service-management baseline is **system-level systemd**, not the SWPC `systemctl --user` model.

Intended Linux roots are:

```text
/opt/plasma/
├── releases/
└── current -> releases/<version>/

/etc/plasma/
/var/lib/plasma/
/var/log/plasma/
```

Installation and upgrade may therefore require elevated privilege. Exact installer mechanics remain to be implemented and validated.

### 2.3 SWPC integration host

SWPC remains an engineering environment:

```text
Development / integration / staging / diagnostics
```

`scripts/plasmactl` remains the source of truth for this integration-host workflow until it is deliberately refactored. Its current assumptions include a Git worktree, Linux `systemctl --user`, Python development dependencies, Node/npm, and a Vite development/demo service. Those assumptions must not be copied into product installers.

## 3. Release artifact principle

Product deployment must consume immutable, versioned release artifacts rather than perform `git pull main` on the target.

Target model:

```text
Git commit
   -> CI / release build
   -> validated role-specific artifact
   -> SHA-256 / release metadata
   -> install into versioned release directory
   -> activate `current`
   -> service reconciliation
   -> health/runtime acceptance
```

At minimum, release metadata must eventually identify:

```text
product version
Git commit SHA
role: control-station | ppu
platform / architecture
build timestamp
artifact SHA-256
runtime compatibility metadata
```

Expected role-specific artifacts are conceptually separate, for example:

```text
plasma-control-station-macos-arm64-<version>.*
plasma-ppu-linux-armv7l-<version>.*
```

The exact archive/container format is intentionally not frozen in this foundation PR.

## 4. Build-time versus target-runtime dependencies

A product target should not need build tooling merely because the source repository needs it.

### Control Station runtime

Current source facts require Python >= 3.11 for Manager and Node.js >= 22.13 for the existing Control Console server runtime. `npm`, Git, and GNU `timeout` are build/development tools and are not accepted as mandatory product deployment mechanics.

The current Web build helper uses GNU `timeout`; macOS does not provide GNU `timeout` by default. This is one reason the Control Station should consume a prebuilt validated Console artifact instead of compiling the Web application during installation.

Future release packaging may bundle runtime dependencies and thereby reduce external prerequisites. Until implemented, the read-only audit reports the current Node runtime dependency explicitly.

### PPU runtime

PPU product runtime requires Python >= 3.11 and systemd. Node.js, npm, Git, and Vite are not PPU product dependencies.

## 5. Configuration ownership

Product deployment configuration follows the existing configuration-architecture rules: persistent configuration is authoritative input; generated service definitions are derived state.

Control Station configuration includes, at minimum:

```text
Manager bind/listen policy
Manager PPU registry
Manager/BFF selected PPU routing identity where applicable
Console/BFF listen policy
logging / state paths
```

PPU configuration includes, at minimum:

```text
facility_id
ppu_id / stable device identity
Gateway bind/listen policy
Plasma Server endpoint
Site topology/capability
provider / hardware profile
logging / state paths
```

IP addresses are routing attributes, not stable PPU identity. Browser storage must not become the authoritative PPU registry.

Secrets must remain outside Git and follow a separate protected lifecycle.

## 6. Product deployment CLI direction

The operator-facing lifecycle should converge on one product deployment interface with role-aware platform backends:

```text
plasma-deploy audit <role>
plasma-deploy install <artifact>
plasma-deploy status
plasma-deploy health
plasma-deploy upgrade <artifact>
plasma-deploy rollback
plasma-deploy version
```

Only the read-only `audit` command exists in the first foundation step. Future mutation commands must be idempotent, version-aware, fail closed, and covered by tests before activation on a real Control Station or PPU.

The existing integration-host `plasmactl` remains separate. Do not silently change `plasmactl` into a product installer while SWPC still depends on its current behavior.

## 7. Read-only readiness audit

The repository provides:

```bash
python3 scripts/product-deploy.py audit control-station
python3 scripts/product-deploy.py audit control-station --json
python3 scripts/product-deploy.py audit ppu
python3 scripts/product-deploy.py audit ppu --json
```

The audit is intentionally non-mutating. It does not install dependencies, create directories, modify services, update Git, load an FPGA bitstream, touch PL, change target power, or program an IC.

### Control Station audit

It checks the current baseline for:

- macOS/Darwin;
- supported Mac architecture;
- Python >= 3.11;
- `launchctl`;
- Node.js >= 22.13 for the current Console server runtime;
- writable user Library root;
- explicit non-requirement of npm, Git, and GNU `timeout` as target deployment mechanics.

### PPU audit

It checks the current baseline for:

- Linux;
- ARM target architecture classification;
- Python >= 3.11;
- `systemctl` and an active systemd runtime directory;
- OS identity source;
- basic network diagnostic tooling;
- explicit non-requirement of Node.js, npm, and Git;
- explicit hardware safety boundary.

An audit result of `READY` means only that the inspected host meets the currently encoded software prerequisites. It is not deployment acceptance and not hardware acceptance.

## 8. Upgrade and rollback contract

The target product lifecycle is versioned activation, not in-place mutation:

```text
current -> release N

install release N+1
  -> validate artifact
  -> install side-by-side
  -> reconcile config/services
  -> health/runtime acceptance
  -> activate current=N+1

failure
  -> restore previous activation
  -> restart previous services
  -> verify health
```

A future installer must retain enough previous release state for deterministic rollback. Configuration migration needs its own forward/backward compatibility rules; rollback must never silently reinterpret incompatible persisted state.

## 9. Acceptance layers

Product deployment evidence remains separated from hardware evidence:

```text
Release/installer validation
    ↓
Host deployment acceptance
    ↓
Managed runtime acceptance
    ↓
Z2 PS acceptance
    ↓
PS <-> PL acceptance
    ↓
PL <-> Site electrical acceptance
    ↓
real IC acceptance
```

For the first product runtime milestone, SWPC must not appear in the production data path:

```text
Mac Control Station
  -> Manager
  -> Z2 PPU
  -> PS Loopback
```

Only after that milestone should a separate approved hardware phase proceed to PS <-> PL and real target work.

## 10. Implementation sequence

The planned implementation sequence is:

1. **Foundation / audit** — role boundaries, non-mutating readiness audit, deployment contract.
2. **Release packaging** — role-specific immutable artifacts and release metadata/SHA-256 validation.
3. **Mac installer** — Control Console + BFF + Manager, configuration, LaunchAgents, health/status.
4. **Z2 installer** — Gateway + Server, configuration, system-level systemd, health/status.
5. **Upgrade/rollback** — side-by-side version activation and deterministic recovery.
6. **Product runtime acceptance** — Mac -> Manager -> Z2 -> PS Loopback with SWPC absent from the runtime chain.
7. **Hardware acceptance** — separate PS <-> PL, Site, and real IC phases.

No later phase may use Mock or software-only evidence to claim hardware acceptance.
