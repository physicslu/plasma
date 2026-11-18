# ADR-0004 — FPGA Image Lifecycle and Programming-Flow Loading

> **Status: Accepted** (owner decision 2026-11-02). Programming-flow FPGA loading is a **decided direction and NOT YET IMPLEMENTED**; see *Migration gap*.
>
> **Supersedes:** [ADR-0003](0003-runtime-fpga-driver-reconfiguration-boundary.md) where it treats runtime bitstream reload / A/B images as deferred or excluded by design.
>
> **Related:** [FPGA contract](../development/plasma-fpga.md), [Embedded contract](../development/plasma-embedded.md), [Bundle v3](../architecture/ppu-canonical-bundle-packages.md), [Single Active Asset Set](../architecture/ppu-job-driven-package-resolution.md), [FPGA Image Asset Handoff](../deployment/ppu-fpga-asset-handoff-gate1.md), [OpenOCD architecture](../architecture/ic-support-openocd-plan-executor.md).
>
> This ADR authorizes no deployment, FPGA load or DUT operation.

## Context

ADR-0003 (Proposed, 2026-10-17 amendment) made one fixed Universal FPGA image the first-generation baseline and listed FPGA Manager reload and A/B images as deferred alternatives. Since then the project loads distinct paired images through Linux FPGA Manager (for example the Blue Pill SWD image), and Bundle v3 can deliver `fpga-image` Packages inside a PPU Asset Set. The repository had no accepted record of the image lifecycle rules or of when a required image is loaded.

## Decision

### 1. Current rules (restated from the current contracts)

- **Image + Manifest pairing.** Every FPGA BIN is delivered with its companion Manifest (`plasma.fpga.image.v1`). Before an authorized load, the protected Root checks the actual SHA256, board/FPGA part, ABI/identity, ownership/leases and Golden recovery prerequisites.
- **Keep Loaded.** After a proven successful FPGA Manager Download (genuine receipt, same-boot identity, exclusive ownership, safe state) the image stays loaded by default. A downstream MMIO/ABI or DPIDR FAIL is a test result, not a Golden Restore trigger.
- **Golden Restore** is invoked only on explicit selection or a documented fault-recovery need. Failed/unknown load, unsafe or in-flight state, or an unreaped owner fail closed without blind retry.
- **Execution boundary.** Z2 PS runs live OpenOCD and its PS-local WordPort/RemoteBitbang bridge; Z2 PL performs SWD/SPI pin I/O; SWPC never hosts live target OpenOCD.

### 2. Programming-flow loading (new decision)

1. **Console decides delivery.** The Console/Controller selects which FPGA Package is delivered to a PPU, as part of the Asset Set carried by a Bundle v3 archive (`fpga-image` Package: prebuilt BIN + HWH + paired Manifest).
2. **PS loads on entering the programming flow.** When a programming flow starts, before any Site begins hardware work, the PS **FPGA Hardware Manager** (the single PPU FPGA configuration owner) compares the bitstream currently loaded in PL with the image the Job requires. If they differ, it loads the required image through Linux FPGA Manager, replacing the current image directly; no intermediate Golden load is required. No separate Console "load FPGA" command is needed.
3. **Checks before loading.** All Sites quiescent and no hardware consumers; exclusive ownership; Manifest/BIN SHA256, board/part and ABI/identity match; safe electrical/PL output state; recovery prerequisites. If any check fails the PPU reports **NOT_READY**, no Site work starts, and no substitute image is chosen.
4. **PPU level, not Site level.** Loading is a PPU-wide step. A SiteWorker never reloads the FPGA.
5. After a successful load, the Keep Loaded rules in §1 apply.

## Consequences

- ADR-0003's "runtime reload not required / excluded by design" position no longer governs. Its UIO/driver analysis remains reference material.
- [ppu-job-driven-package-resolution.md](../architecture/ppu-job-driven-package-resolution.md) is aligned with this ADR: an FPGA image mismatch is resolved by the PS FPGA Hardware Manager when the programming flow starts, not by a separate Console-authorized operation.
- Asset Set activation and FPGA configuration remain distinct steps; activating a Set does not by itself reload the FPGA.

## Migration gap (not implemented)

- Implemented today, host-only: Bundle v3 admission and install of Asset Sets, and read-only FPGA handoff resolution reporting `VERIFIED_NOT_LOADED` (see the handoff document).
- Not implemented: the programming-flow compare-and-load step, the FPGA Hardware Manager service integration with the Programming Runtime, and a qualified physical load via Bundle-delivered `fpga-image` Packages. Until they exist, FPGA images are loaded through the existing protected Root Entry procedures.
