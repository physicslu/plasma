# Plasma Deployment Notes

`scripts/plasmactl` is the profile-aware operator entry point for integration-host, local Control Station, SWPC Z2-like surrogate, and Real Z2 PS-only deployment roles. Profile-specific backends preserve separate ownership and qualification boundaries; a common CLI does not make those roles interchangeable.

- **Current** — [`plasmactl` Deployment Profiles](plasmactl-deployment-profiles.md): canonical profile router, role ownership, immutable deployment behavior, and qualification boundaries for `integration`, `local-control-station`, `swpc-z2like`, and `z2-ps`.
- **Current** — [Deployment Port / Profile Matrix](port-profile-matrix.md): canonical cross-profile meaning of `9900`, `18080`, `18081`, `18082`, `18180`, `18190`, `18280`, and the integration-only `5173` development runtime.
- **Current simulation architecture** — `z2like-demo`: SWPC is the single Simulation Environment; its canonical public-demo PPU backend is one persistent QEMU ARMv7 simulated Z2 on SWPC. Private Bootstrap stays on the Docker bridge, while public managed Programming uses a separate Cloudflare Access-protected SWPC ingress on `127.0.0.1:18083`. The x86_64 `swpc-z2like` profile remains an engineering surrogate, not the `z2like-demo` backend. See the dedicated section below.
- **Current foundation** — [Product Deployment Foundation](product-deployment-foundation.md): cross-platform Control Station (macOS/Linux/Windows) / Z2 PPU role boundaries, immutable release direction, platform service-manager adapters, and the implemented read-only product readiness audit.
- **Current** — [Product Release Format v1](product-release-format.md): canonical product version metadata, role/platform artifact matrix, `release.json`, detached archive SHA-256, internal `SHA256SUMS`, safe verification, and clean-extraction acceptance.
- **Current** — [Control Station Runtime Packaging](control-station-runtime-packaging.md): source-tree-independent Vinext standalone Console/BFF, Manager Python zipapp, Control Station release orchestration, and macOS/Linux/Windows clean-runtime acceptance.
- **Z2 PS Phase 1** — [PPU Runtime Packaging](ppu-runtime-packaging.md): source-tree-independent PPU Python zipapp, canonical `linux-armv7l` PPU release, fail-closed PS-only configuration, systemd topology, Manager enrollment, and Managed PS Loopback acceptance boundary.
- **Z2 PS installer** — [PYNQ-Z2 PS Installer and Managed Loopback Acceptance](z2-ps-installer.md): verified release consumption, PYNQ/System-Python isolation, immutable side-by-side installation, explicit isolated Python >= 3.11 binding, P3 bounded runtime activation, systemd activation/rollback, Z2-local readiness, and the separate Managed PS Loopback qualification boundary.
- **Render -> SWPC managed PS lab reference** — [Render Control Station -> SWPC Z2-like PPU Managed PS Loopback](render-swpc-managed-ps-loopback.md): earlier PS-loopback foundation for the separate Render-hosted Control Station/Manager and SWPC surrogate. It is retained as historical/reference evidence; it is not the canonical `z2like-demo` backend after QEMU convergence.
- **macOS installer pilot** — [macOS Control Station Installer Pilot](macos-control-station-installer-pilot.md): unsigned `.pkg`, immutable `/Library/Application Support/Plasma` runtime, per-user `launchd` LaunchAgents, absolute external Node/Python runtime binding, install/restart/stop-start/basic-uninstall acceptance, and downloadable CI artifact.
- **Windows installer pilot** — [Windows Control Station Installer Pilot](windows-control-station-installer-pilot.md): unsigned MSI, immutable versioned `%ProgramFiles%` runtime, mutable `%ProgramData%` state, WinSW-backed Windows SCM services, install/restart/stop-start/basic-uninstall acceptance, and downloadable CI artifact.
- **Historical public-preview reference** — [SWPC Public Preview / Mock Environment](swpc-public-preview.md): retained evidence for the earlier `plasma.open4th.com` preview topology. It is not the canonical current PPU/Control Station routing contract.
- Integration-host installation, configuration, update, verification and service control: [Integration Host Deployment Guide](../development/swpc-deployment.md).
- Linux local Control Station: [Local Control Station Reference Deployment](local-control-station.md).
- SWPC configured Mock Programming: [SWPC Z2-like Configured Mock Programming](swpc-z2like-configured-mock-programming.md).
- SWPC managed Programming ingress: [SWPC Z2-like Managed Programming Ingress](swpc-z2like-managed-programming-ingress.md).
- Web runtime/HMR lifecycle rules: [Web Runtime Deployment Hygiene](web-runtime-hygiene.md).
- Single-service public Mock deployment: [Render Free Public Mock Demo](render-free-public-demo.md).
- Public API smoke acceptance: [Render Public Smoke Acceptance](render-public-smoke.md).
- Public browser acceptance: [Render Public Browser Acceptance](render-public-browser.md).

The `plasmactl` profile router is now part of the current deployment contract. Legacy commands without an explicit profile remain integration-host commands for backward compatibility; profile-aware commands select separate Control Station, surrogate-PPU, or Real Z2 PS backends. Do not infer that integration-host behavior applies to every profile.

Product release construction remains a separate build-side concern. `scripts/product-release.py` consumes an already-built runtime payload and emits a role/platform-specific immutable artifact; it does not build source code or mutate a target host. Control Station packaging adds `scripts/control-station-release.py` as a narrow policy adapter so the validated Vinext standalone `console/node_modules/**` runtime dependency tree can enter the same Common Release Format without weakening the generic release builder's arbitrary-`node_modules` rejection. PPU packaging similarly adds `scripts/ppu-runtime.py` and `scripts/ppu-release.py` so the Z2 role can consume a validated Python-only runtime without Node/npm or a source checkout.

The macOS and Windows installer pilots are host-mutating Control Station adapters. The macOS pilot is unsigned and non-notarized and the Windows pilot is unsigned; both keep Node.js and Python as external prerequisites and neither represents production signing/distribution readiness. The Real Z2 `z2-ps` profile is implemented as a distinct host-mutating PS-only PPU adapter: it consumes a verified ARMv7 release, binds an explicitly Plasma-owned isolated Python >= 3.11 runtime, installs immutable side-by-side releases and systemd units, preserves canonical Site Desired state on upgrade, and verifies the bounded P3 runtime-activation contract. Current-main `z2-ps` still requires real-board qualification before that revision may be claimed as Real Z2 evidence. It does not qualify PL, OpenOCD, Site electrical behavior, real IC programming, or eight-Site hardware concurrency.

The SWPC Z2-like installer is deliberately a laboratory surrogate adapter, not a second Z2 release format. It mirrors the Z2 PS filesystem, isolated-Python, systemd, release-identity, fail-closed hardware, and bounded runtime-activation ownership boundaries on x86_64 so central managed routing can be qualified before real Z2 deployment. Its canonical configuration may contain one-based Site Desired entries up to the eight-Site capacity; `sites: []` is only a fail-closed first-install bootstrap state, not the permanent product topology. SWPC surrogate evidence must not be used as ARMv7/PYNQ evidence.

## z2like-demo canonical QEMU ARMv7 backend

`SWPC` is the **only Plasma Simulation Environment**. QEMU is not a separate environment; it is the canonical ARMv7 simulated-Z2 backend running inside SWPC for `z2like-demo`.

```text
SWPC
└── Docker/QEMU ARMv7 simulated Z2
    ├── private Gateway    172.29.33.21:18080
    ├── private Bootstrap  172.29.33.21:18081
    └── canonical ARMv7 PPU Runtime
```

The x86_64 `swpc-z2like` profile remains available for fast engineering regression and production-like filesystem/systemd ownership tests. It is no longer the canonical `z2like-demo` PPU backend.

### Private commissioning and Bootstrap acceptance

Bootstrap remains private on the SWPC Docker bridge:

```text
SWPC Local Control Station
  -> local BFF
  -> local mutable Manager / Bootstrap credential store
  -> http://172.29.33.21:18081 Bootstrap
  -> canonical Z2 PS kit
  -> QEMU ARMv7 PPU Runtime
  -> http://172.29.33.21:18080 Gateway
```

Start or inspect the persistent simulation:

```bash
python3 scripts/z2like-qemu-sim.py up
python3 scripts/z2like-qemu-sim.py status --write-evidence
```

The pairing token is intentionally local-only:

```bash
python3 scripts/z2like-qemu-sim.py token
```

Do not place this token in repository files, Render variables, screenshots, CI artifacts, or general logs.

For direct CI/operator Bootstrap acceptance with a canonical Z2 kit:

```bash
python3 scripts/z2like-qemu-bootstrap-smoke.py \
  /path/to/plasma-z2-ps-kit-<release>.tar.gz \
  --sidecar /path/to/plasma-z2-ps-kit-<release>.tar.gz.sha256
```

For product-path acceptance, register `http://172.29.33.21:18080` in the SWPC local Control Station/Manager and use **EMode -> PPU Sites -> Runtime Deployment**. The Manager derives the private Bootstrap endpoint on the same QEMU appliance.

The simulation verifies kit structure/integrity, verifies/stages the canonical PPU release with the current Z2 installer core, and executes the packaged `linux-armv7l` PPU Runtime under ARMv7 QEMU. The Plasma Python artifact inside the kit is integrity-checked as part of the kit but is not installed as the QEMU container interpreter; the simulation uses the pinned ARMv7 container Python.

The QEMU adapter intentionally does **not** emulate systemd. It therefore does not qualify real Z2 service-manager startup, reboot persistence, Unix-socket DAC, or the privileged P3 runtime-activation helper. Software activation failure restores the previous simulated Runtime selection only.

### Public z2like-demo steady-state path

The Render `z2like-demo` service stays a Control Station/Manager and never becomes a public Bootstrap proxy:

```text
Browser
  -> Render z2like-demo Console/BFF
  -> Render Manager
  -> HTTPS Cloudflare Access service-token protected managed hostname
  -> Cloudflare Tunnel
  -> SWPC 127.0.0.1:18083
  -> bounded QEMU managed Programming ingress
  -> 172.29.33.21:18080 QEMU Gateway
  -> QEMU ARMv7 Plasma Server / configured Mock Sites
```

The Render PPU alias is `z2-qemu-ppu`. `PLASMA_RENDER_PPU_ENDPOINT` remains a deployment secret/configuration value and must point to the authenticated HTTPS managed hostname, never directly to the Docker bridge.

SWPC host port ownership remains distinct:

```text
18080  x86 swpc-z2like full local Gateway
18081  x86 swpc-z2like restricted diagnostics/status ingress
18082  x86 swpc-z2like managed Programming ingress
18083  z2like-demo QEMU ARMv7 managed Programming ingress
```

Install the QEMU public ingress only after the QEMU evidence reports `runtime_active`:

```bash
sudo bash scripts/plasmactl-z2like-qemu-managed-ingress install
sudo bash scripts/plasmactl-z2like-qemu-managed-ingress verify
```

Cloudflare Tunnel for the z2like-demo managed PPU hostname must target `http://127.0.0.1:18083`. Cloudflare Access must require a Render-specific service token, and unauthenticated requests must be denied at the edge before switching the Render endpoint.

The QEMU public ingress deliberately returns `404` for `/api/settings/sites/activation`. The simulation has no real privileged systemd/runtime-activation helper, so exposing that side effect would manufacture capability. Programming uses the canonical initial Mock Site configuration instead.

The Z2 PS release workflow now builds the canonical kit, starts this QEMU ARMv7 appliance, uploads the kit over the authenticated private Bootstrap API, activates the packaged PPU release, and requires Gateway readiness. This is ARMv7 software/package evidence, not physical Z2 evidence.

A PASS supports only:

```text
SWPC simulation environment
+ QEMU ARMv7 userspace
+ Bootstrap identity/token/upload/deployment API
+ canonical Z2 PS kit integrity
+ canonical PPU release verification/staging
+ ARMv7 Plasma Server/Gateway execution
+ configured Mock Site programming path
+ software activation rollback
```

It does **not** qualify PYNQ-Z2 hardware, real systemd/reboot persistence, real privileged runtime-activation helper/DAC, PS-to-PL, FPGA, Site electrical behavior, target power, physical OpenOCD, real IC erase/program/verify, or physical multi-Site concurrency.

**Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED.**

## Software-debt closure boundary before Real Z2 PS-only

As of 2026-09-13, `SOFTWARE-DEBT-CLOSED` is a semantic software gate, not a hardware-readiness claim. A3 leaves only bounded `pass` cases for `asyncio.CancelledError` task-drain, already-absent socket/file cleanup, and retry-backoff timeout completion; these do not authorize suppressing power/reset shutdown failures. A4 is closed by the shared `test_batch_runtime_contract.py` semantics across the Batch runtime inheritance hierarchy—the contract, not the number of runtime classes, is authoritative. A5 requires every retained deployed/legacy startup path to use explicit handler composition through `gateway_runner.serve_handler` and forbids runtime replacement of `gateway.PlasmaWebHandler`. A6 evidence on SWPC recorded `sudo bash scripts/plasmactl deploy swpc-z2like` PASS, `sudo bash scripts/plasmactl verify swpc-z2like` PASS, plus PMode, EMode, and PS Loop Test PASS.

This gate explicitly does **not** close concrete production `SiteSafetyControl`, real OpenOCD erase/program/verify, PYNQ-Z2 ARMv7 physical qualification of the current release, PL/FPGA integration, Site electrical behavior, real-IC evidence, or 1-/N-/8-Site hardware concurrency. The Engineering 8×32 topology remains intentional simulation infrastructure, not production topology evidence. Passing this gate authorizes starting Real Z2 PS-only qualification; it does not establish `z2-full` or production programmer readiness.

Deployment, restart, service mutation, public routing changes and rollback are protected operations. Documentation and tests do not authorize executing them; follow the repository Two-Gate Model and the approved plan for the exact environment and action.
