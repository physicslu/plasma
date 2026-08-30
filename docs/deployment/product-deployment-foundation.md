# Plasma Product Deployment Foundation

> Status: **Plan with implemented foundations**. This document defines the approved product deployment direction. The read-only readiness audit, Common Release Format, and common Control Station runtime are implemented; the macOS Control Station adapter now has an unsigned installer pilot. Full signing/notarization, Linux/Windows adapters, upgrade/rollback, and Z2 runtime acceptance remain separate work.

## 1. Purpose

Plasma must stop treating the SWPC integration host as the product runtime topology. SWPC remains useful for development, CI-adjacent integration, staging, and diagnostics, but product deployment is split into explicit **product roles** rather than development machines or operating systems.

```text
Control Station
├── macOS
├── Linux
└── Windows
     |
     | hosts the same product role
     v
├── Plasma Control Console
├── Manager BFF runtime
└── Plasma Manager
        |
        | managed network route
        v
PPU / embedded Linux
├── PPU Gateway
├── Plasma Server
└── PS -> PL -> Site hardware path
```

The current hardware development target for the PPU role is PYNQ-Z2.

The first product acceptance path is intentionally narrower than hardware acceptance:

```text
Control Station Console/BFF
  -> Manager
  -> Z2 Gateway
  -> Z2 Plasma Server
  -> Z2 PS diagnostic handler
  -> return
```

A passing managed PS Loopback proves the deployed software node and managed route. It does not prove PS <-> PL, FPGA execution, Site electrical behavior, or real IC programming.

## 2. First-principles deployment model

The canonical deployment abstraction is:

```text
Product role
    ↓
Common runtime contract
    ↓
Platform / service-manager adapter
```

Operating-system-specific service mechanics must not leak into the Control Console, Manager routing contract, PPU execution contract, or product identity model.

Conceptually:

```text
                         plasma-deploy
                              |
              +---------------+---------------+
              |                               |
       control-station                       ppu
              |                               |
     +--------+---------+                     |
     |        |         |                     |
   macOS    Linux    Windows              embedded Linux
     |        |         |                     |
  launchd  systemd   Windows SCM            systemd
```

`Linux Control Station` and `Linux PPU` are different product roles even though both use Linux and systemd.

## 3. Deployment roles

### 3.1 Control Station

The Control Station is the operator/fleet product role. It owns:

- Plasma Control Console;
- same-host Manager BFF runtime;
- Plasma Manager;
- PPU registry and fleet-level routing configuration;
- operator-facing logs and effective-version observability.

It does **not** own PPU Site execution, FPGA behavior, target power, or real IC programming.

The planned Control Station platform baseline is:

| Platform | Planned architecture baseline | Service lifecycle owner |
|---|---|---|
| macOS | arm64, x86_64 | `launchd` LaunchAgent |
| Linux | x86_64, arm64 | system-level `systemd` |
| Windows | x86_64 | Windows Service Control Manager (SCM) |

These are planned release targets. A passing platform-specific installer or CI result applies only to that platform and does not prove the other adapters.

#### macOS persistence baseline

The macOS adapter separates immutable, system-owned application releases from mutable per-user state:

```text
/Library/Application Support/Plasma/
├── releases/
│   └── <version>/
├── current -> releases/<version>/
└── install/

~/Library/Application Support/Plasma/
├── config/
└── state/

~/Library/Logs/Plasma/
~/Library/LaunchAgents/
```

This split avoids requiring a root-run `.pkg` payload phase to guess an operator home directory. The package lays down immutable runtime under `/Library/Application Support/Plasma`; post-install reconciliation creates per-user mutable state and LaunchAgents for the selected operator account.

The v1 macOS service baseline is per-user `launchd` LaunchAgents because the Control Station is an operator-facing desktop role. The current macOS installer pilot is unsigned and non-notarized and therefore is validation evidence, not production Apple distribution readiness.

#### Linux Control Station persistence baseline

```text
/opt/plasma/
├── releases/
└── current -> releases/<version>/

/etc/plasma/
/var/lib/plasma/
/var/log/plasma/
```

The v1 Linux Control Station service baseline is system-level `systemd`.

#### Windows Control Station persistence baseline

Conceptually:

```text
%ProgramFiles%\Plasma\
├── releases\
└── current\

%ProgramData%\Plasma\
├── config\
├── state\
└── logs\
```

The Windows lifecycle owner is Windows Service Control Manager. The exact service-wrapper implementation is deliberately not frozen in this foundation step. A future implementation may use a native service launcher or another maintainable SCM-compatible wrapper, but **Task Scheduler is not the product service lifecycle contract**.

Linux and Windows installer mechanics remain to be implemented and validated before those platform adapters become Current deployment behavior.

### 3.2 PPU

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

### 3.3 SWPC integration host

SWPC remains an engineering environment:

```text
Development / integration / staging / diagnostics
```

`scripts/plasmactl` remains the source of truth for this integration-host workflow until it is deliberately refactored. Its current assumptions include a Git worktree, Linux `systemctl --user`, Python development dependencies, Node/npm, and a Vite development/demo service. Those assumptions must not be copied into product installers.

## 4. Release artifact principle

Product deployment must consume immutable, versioned release artifacts rather than perform `git pull main` on the target.

Target model:

```text
Git commit
   -> CI / release build
   -> validated role-specific artifact
   -> SHA-256 / release metadata
   -> install into versioned release directory
   -> activate current release
   -> service reconciliation
   -> health/runtime acceptance
```

At minimum, release metadata must eventually identify:

```text
product version
Git commit SHA
role: control-station | ppu
platform
architecture
build timestamp
artifact SHA-256
runtime compatibility metadata
```

### 4.1 Planned artifact matrix

Control Station release targets are conceptually:

```text
plasma-control-station-macos-arm64-<version>.*
plasma-control-station-macos-x86_64-<version>.*
plasma-control-station-linux-x86_64-<version>.*
plasma-control-station-linux-arm64-<version>.*
plasma-control-station-windows-x86_64-<version>.*
```

The current PPU target is conceptually:

```text
plasma-ppu-linux-armv7l-<version>.*
```

The Common Release Format is defined independently from installer containers. The macOS installer pilot additionally emits an unsigned `.pkg`; that does not freeze the future Linux or Windows installer format.

### 4.2 Common payload versus platform adapter

The product should avoid three independent Control Station implementations. The intended separation is:

```text
Control Station common runtime payload
├── Console/BFF application
├── Manager runtime
├── product metadata
└── common configuration model

Platform adapter
├── macOS launchd definitions / paths
├── Linux systemd definitions / paths
└── Windows SCM definitions / paths
```

Application behavior and API contracts should remain common. Platform differences belong in packaging, service management, filesystem placement, and privilege handling.

## 5. Build-time versus target-runtime dependencies

A product target should not need build tooling merely because the source repository needs it.

### Control Station runtime

Current source facts require Python >= 3.11 for Manager and Node.js >= 22.13 for the existing Control Console server runtime. `npm`, Git, and GNU `timeout` are build/development tools and are not accepted as mandatory product deployment mechanics.

The current Web build helper uses GNU `timeout`. That dependency is another reason Control Stations should consume prebuilt validated Console artifacts rather than compile the Web application during installation. Windows should not need a Unix compatibility layer merely to install Plasma.

The macOS installer pilot keeps Python and Node external and resolves validated absolute executable paths for `launchd`; it does not depend on interactive shell profile initialization. Future release packaging may bundle Python/Node runtimes and thereby reduce external prerequisites.

### PPU runtime

PPU product runtime requires Python >= 3.11 and systemd. Node.js, npm, Git, and Vite are not PPU product dependencies.

## 6. Configuration ownership

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

Secrets must remain outside Git and follow a separate protected lifecycle. Platform-specific secret storage may differ, but the application must not invent separate security semantics for each OS.

## 7. Product deployment CLI direction

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

Only the read-only `audit` command exists in the common product-deploy foundation. The macOS pilot currently uses dedicated packaging/service scripts to validate the platform adapter; it does not redefine the final cross-platform CLI contract. Future mutation commands must be idempotent, version-aware, fail closed, and covered by tests before activation on a real Control Station or PPU.

The same operator-level lifecycle should hide platform mechanics. A normal operator should not need to know or directly invoke:

```text
launchctl
systemctl
sc.exe
npm
pip
git
```

The existing integration-host `plasmactl` remains separate. Do not silently change `plasmactl` into a product installer while SWPC still depends on its current behavior.

## 8. Read-only readiness audit

The repository provides:

```bash
python3 scripts/product-deploy.py audit control-station
python3 scripts/product-deploy.py audit control-station --json
python3 scripts/product-deploy.py audit ppu
python3 scripts/product-deploy.py audit ppu --json
```

The audit is intentionally non-mutating. It does not install dependencies, create directories, modify services, update Git, load an FPGA bitstream, touch PL, change target power, or program an IC.

### 8.1 Control Station audit

The same `control-station` role auto-detects the host OS and architecture.

Common checks include:

- supported Control Station OS/architecture target;
- Python >= 3.11;
- Node.js >= 22.13 for the current Console server runtime;
- explicit non-requirement of npm, Git, and GNU `timeout` as target deployment mechanics.

Platform-specific checks are:

| Platform | Audit service check | Planned target identity |
|---|---|---|
| macOS arm64/x86_64 | `launchctl` + writable user Library | `macos-<arch>` |
| Linux x86_64/arm64 | `systemctl` + active systemd runtime | `linux-<arch>` |
| Windows x86_64 | SCM command + ProgramFiles/ProgramData roots | `windows-x86_64` |

Unsupported OS or architecture combinations fail closed rather than being reported READY.

### 8.2 PPU audit

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

## 9. Upgrade and rollback contract

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

A future production installer must retain enough previous release state for deterministic rollback. Configuration migration needs its own forward/backward compatibility rules; rollback must never silently reinterpret incompatible persisted state.

The macOS installer pilot intentionally validates installation and basic service lifecycle only; it does not claim upgrade migration or rollback.

Windows may not implement the `current` abstraction as a Unix symbolic link. The product contract is **versioned side-by-side activation with deterministic rollback**; platform adapters may realize that abstraction differently while preserving the same behavior.

## 10. Acceptance layers

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
Control Station
  -> Manager
  -> Z2 PPU
  -> PS Loopback
```

A Control Station deployment claim is platform-specific. Passing on macOS does not prove the Windows installer, and passing on Linux does not prove the macOS service adapter. The common application contract can be shared, but each released platform artifact needs its own packaging/deployment evidence.

Only after the managed Z2 PS milestone should a separate approved hardware phase proceed to PS <-> PL and real target work.

## 11. Planned validation matrix

The release pipeline should progressively cover:

| Role | Platform | Validation intent |
|---|---|---|
| Control Station | macOS arm64 | real operator-host deployment and runtime acceptance |
| Control Station | macOS x86_64 | build/package compatibility if retained as a release target |
| Control Station | Linux x86_64 | CI/package plus real deployment acceptance |
| Control Station | Linux arm64 | build/package compatibility where supported |
| Control Station | Windows x86_64 | CI/package plus real deployment acceptance |
| PPU | Z2 embedded Linux / armv7l | real target deployment and managed PS acceptance |

A target should be removed from the release matrix rather than retained as an untested marketing claim if we cannot maintain credible build and deployment validation for it.

## 12. Implementation sequence

The planned implementation sequence is:

1. **Foundation / audit** — role boundaries, cross-platform non-mutating readiness audit, deployment contract. **Implemented.**
2. **Common release format** — immutable metadata, SHA-256 validation, role/platform/architecture identity. **Implemented.**
3. **Control Station runtime package** — common Console/BFF + Manager payload independent of service manager. **Implemented.**
4. **Control Station platform adapters** — macOS launchd, Linux systemd, Windows SCM installers/service definitions. **macOS unsigned installer pilot implemented; Linux/Windows pending.**
5. **PPU release package** — Gateway + Server artifact for embedded Linux/Z2 without Node/npm/Vite.
6. **Install / upgrade / rollback** — role-aware platform lifecycle and deterministic recovery. The macOS pilot covers initial install and basic lifecycle/uninstall, not full upgrade/rollback.
7. **Product runtime acceptance** — selected Control Station platform -> Manager -> Z2 -> PS Loopback with SWPC absent from the runtime chain.
8. **Cross-platform Control Station acceptance** — validate each platform artifact before claiming it as supported.
9. **Hardware acceptance** — separate PS <-> PL, Site, and real IC phases.

No later phase may use Mock or software-only evidence to claim hardware acceptance.
