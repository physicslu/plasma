# PLASMA Glossary

Short definitions of terms as they are **currently used** in this repository. This page adds no rules; each entry points to the authoritative document. When a definition here disagrees with code or a linked contract, the code/contract wins (see [AGENTS.md](../AGENTS.md) source priority).

## Product hierarchy and hosts

### Facility / PPU / SITE / Socket
- **Facility** — a deployment containing one or more PPUs.
- **PPU** — one programmer unit; the prototype target is a PYNQ-Z2 (Zynq-7020, XC7Z020).
- **SITE** — an independent programming position inside a PPU, identified by one-based `site_id` 1..N. Retired zero-based Channel/Programmer identity must not return.
- **Socket** — a physical fixture; it is not Site identity.

See [AGENTS.md](../AGENTS.md) and [PPU Facility Sites](architecture/ppu-facility-sites.md).

### SWPC
The workstation/control station. It runs Web / Controller / BFF and sends high-level commands over Ethernet. It may build or host-test OpenOCD but never hosts live target OpenOCD or forwards per-bit SWD traffic. See [OpenOCD architecture](architecture/ic-support-openocd-plan-executor.md).

### Z2 PS / Z2 PL
- **PS** — the Zynq ARM processing system running embedded Linux and the programming runtime, including live OpenOCD and its PS-local WordPort/RemoteBitbang bridge.
- **PL** — the FPGA fabric performing SWD/SPI pin I/O toward the DUT.

See [Embedded contract](development/plasma-embedded.md) and [FPGA contract](development/plasma-fpga.md).

### Plasma Gateway vs Linux Default Gateway
**Plasma Gateway** is the PPU service (its **Plasma Gateway API** and **Plasma Gateway Endpoint**; standard-library HTTP + REST polling, integration port normally 18080). The Linux **Default Gateway** is an unrelated layer-3 next hop. Never conflate them. See [Control-plane routing](architecture/control-plane-routing-architecture.md).

### Plasma Manager
Bounded managed PPU routing/relay — not a central universal scheduler. See [Manager contract](development/plasma-manager.md).

## Programming data

### OPF (Open Programming Framework)
**OPF** is the portable, Host-independent programming framework contract covering Provider capabilities, operations and results. A **Provider** is a pluggable implementation under OPF, not the expansion of the OPF acronym. The former name **Open Provider Framework** is historical; this terminology update does not change identifiers, on-wire schemas, Job execution ownership or hardware safety rules. See [OPF architecture](architecture/opf-architecture.md).

### Programming Asset / Normalized Image
A **Programming Asset** is the user-supplied input (e.g. a firmware file); the **Normalized Image** is the execution model derived from it. See [Common contract](development/plasma-development-common.md).

### Recipe / Package (programming) vs Bundle v3 Package
The programming **Recipe/Package** concept (how an IC is programmed) is still evolving and is **not** the same thing as a **Bundle v3 Package** (a deployable unit inside a PPU Bundle). See below.

## PPU deployment

### Bundle / Package / Files (Bundle v3)
Canonical deployment hierarchy **Bundle → Packages → Files**: `plasma.ppu.bundle.v3`, manifest `packages[]` (1–32), each Package with `id`, `kind` (e.g. `python`, `native-c`, `fpga-image`), `version`, `requires`, `files`. See [Bundle v3 contract](architecture/ppu-canonical-bundle-packages.md).

Not to be confused with the **`ppu-bootstrap-factory-bundle`** CI artifact, which is the factory Bootstrap installer kit, not a `plasma.ppu.bundle.v3` archive.

### Factory / Factory Bootstrap
The initial, locally installed PPU Bootstrap service (Installer Core, verifier and device policy) that later accepts Bundle uploads. See [PPU Bootstrap factory](deployment/ppu-bootstrap-factory-and-hil.md).

### B1/B2/B3
This label has **three unrelated meanings**; documents using it carry a term note saying which one applies.

| Context | B1 | B2 | B3 | B4 |
| --- | --- | --- | --- | --- |
| **Bundle stages** ([Bundle v3 assets](deployment/ppu-bundle-v3-generic-assets-gate1.md)) | upload / commit (`POST /v1/uploads`) | admission (`POST /v1/deployments`, data-only receipt) | install / verify; with explicit `fpga_load: true` also FPGA load + Active Set | activation, incl. previous-version backup (not implemented) |
| **FPGA/UIO safety items** from PR #972 ([runtime FPGA architecture](architecture/runtime-fpga-architecture-v1.md)) | live Fabric UIO ownership handoff | retained-mmap guard | aperture Supervisor | – |
| **Governance blocking decisions** (former development-blocking policy) | authorization and source | Z2 hardware safety / recovery | authentic receipt | – |

The governance meaning came from a policy document that has been retired; it survives only in older text such as [todo.md](development/todo.md).

## Approval and execution

### Gate 1 / Gate 2
The only two owner approval gates: **Gate 1** approves a bounded plan before implementation; **Gate 2** approves merging one specific merge-ready PR. See [AGENTS.md](../AGENTS.md).

### ChatGPT Direct / Path 2 / Path 3
- **ChatGPT Direct** — the default, unnumbered route for code, docs and host-only CI (formerly "Path 1").
- **Path 2** — deterministic SWPC CLI work. See [Path 2 contract](development/plasma-path2-cli.md).
- **Path 3** — SWPC Codex for autonomous diagnosis/repair and approved hardware tasks. See [Path 3 contract](development/plasma-path3-codex.md).

### Development Mode
The default owner-operated prototype mode: optimize Build → Run → Observe → Fix without removing electrical, permission, ownership or recovery guards. See [AGENTS.md](../AGENTS.md).

### M1 (Architecture Freeze)
A fixed-image FPGA architecture milestone. Many Gate 1 documents state "M1 Architecture Freeze = NO-GO"; acceptance criteria are in [Fixed FPGA M1 acceptance](architecture/fixed-fpga-m1-gate1-acceptance.md). There is no later M1 decision record.

## FPGA image lifecycle

### Image + Manifest
A PL bitstream (BIN) is delivered together with its companion Manifest (`plasma.fpga.image.v1`); the protected Root validates the BIN SHA256, board/FPGA part and ABI/identity against it. See [FPGA contract](development/plasma-fpga.md) and [ADR-0004](adr/0004-fpga-image-lifecycle-and-job-driven-loading.md).

### Golden / Keep Loaded
- **Golden** — the verified recovery image (`base.bin`), used for explicit or fault-driven Restore.
- **Keep Loaded** — after a proven successful FPGA Download the image stays in PL by default; a functional test FAIL is not a Restore trigger.

See [Embedded contract](development/plasma-embedded.md).

### Protected Root Entry
`scripts/z2/plasma-path2-root-entry`, the guarded entry for privileged Z2 FPGA Manager image lifecycle/recovery operations, validating operation and source SHA.

### WordPort / RemoteBitbang (RBB)
OpenOCD's `remote_bitbang` SWD commands, served on a PS-local UNIX socket and translated into fixed 32-bit MMIO reads/writes of the PL SWD image (`scripts/bluepill-wordport-session.py`, `software/python/plasma_interfaces/bluepill_remote_bitbang.py`).

## Retired / historical codes

These codes appear in older documents, tests and code. They are **not** current routes.

- **F1-B** — fixed-ABI Site 1 PS7 Vivado integration, `pl/projects/z2-fixed-unified-site1`. **Retired and deleted** (owner decision 2026-11-02); see Git history for its sources.
- **z2-swd-gpio** — PS EMIO GPIO software bit-bang FPGA project. Retired; see [SWD retirement map](development/swd-legacy-path-retirement.md).
- **z2-swd03-axi / SWD-03** — FPGA-internal synthetic DPIDR responder (`0x2BA01477`), no external pins. Retired as a physical route.
- **SWD-04 / SWD-05** — historical internal-fixture HIL and synthetic SWD transaction driver; direct CLIs retired.
- **SWD-06** — RTL ↔ Python differential regression for the SWD-05 driver.
- **SWD-00 / PSPL-02** — internal PS–PL waveform loopback experiment; see [PSPL-02 runbook](development/pspl02-swd00-hil-runbook.md).
- **LT02 (MMIO-LT-02)** — internal PS ↔ PL AXI4-Lite loopback image; see [MMIO-LT-02](development/mmio-lt02-ps-pl-loopback.md).
- **MS01 (MMIO-MS-01)** — PR #972 dual-Site six-aperture candidate.
- **HIL-A / A1 / A1.5 / A2** — ARMv7 barrier library: A1 cross-build, A1.5 QEMU execution, A2 native Cortex-A9 execution. See [HIL-A](development/armv7-barrier-hil-a.md), [HIL-A1.5](development/hil-a15-qemu-armv7.md), [HIL-A2](development/hil-a2-cpu-only.md).
- **Bundle v2 / Package v1** — retired PPU deployment wire formats, replaced by Bundle v3.
