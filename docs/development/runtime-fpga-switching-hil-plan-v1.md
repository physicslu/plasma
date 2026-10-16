# Runtime FPGA Phase 1 — Switching HIL Acceptance & Supervisor Contract

> **Status: Plan / Host-only design.** Not a HIL runbook granting execution.
> 
> Related: [Runtime FPGA Roadmap](../architecture/runtime-fpga-architecture-v1.md), [ADR-0003 Proposed](../adr/0003-runtime-fpga-driver-reconfiguration-boundary.md), [Proposed ABI v1](../architecture/runtime-fpga-hardware-abi-v1.md), independent unmerged PR #972.
>
> This Phase 1 PR permits **docs + Host tests + read-only inventory code**, not live Driver bind/unbind, FPGA Manager writes, FPGA reload, target power/reset, MMIO reads, service restart or deployment.

## 1. What we must prove

**User-visible invariant:** When an operator changes an exact IC or requires another programming protocol, Linux, Ethernet and PPU Gateway remain running. Profile-only protocol compatibility should **not** trigger a reload. If PL capability genuinely differs, an approved A/B image transition can occur while all Sites are quiesced. No Site Job is allowed until the selected Image passes ABI and Hardware Admission.

**Not the same acceptance:** Device Profile switch without reload, FPGA A/B reload, and physical programming SWD→SPI are distinct evidence classes.

## 2. Current evidence and hard blockers

| Boundary | Current known evidence | Outcome |
| --- | --- | --- |
| Historical 5-aperture Z2 | prior supervised PS/PL load + original PYNQ `base.bin` restoration | Previous fixture PASS only |
| PR #972 6-aperture MS01 Host | B2 retained-map guard PASS; B3 Supervisor Host PASS; unchanged Vivado candidate | Host-only PASS |
| PR #972 Z2 HIL-A | Fabric UIO driver bound over `0x40000000–0x4000FFFF`; no authorized rebind in later Host work | B1 BLOCKED |
| PR #972 MS01 HIL-B / HIL-C | Not run | NO-GO / NOT RUN |
| Proposed Runtime FPGA ABI v1 | No v1-compliant physical Image A/B yet | NOT IMPLEMENTED |
| FPGA Manager + Bridge | FPGA Manager previously operated; effective Bridge/DT integration unknown for new images | NOT QUALIFIED |

Never reinterpret a skipped test, host fixture, image digest, or `fpga_manager/state=operating` as successful physical programming or safe reload.

## 3. Phase 1 read-only Z2 discovery checklist (NOT executed by this PR)

Collect, pin and independently review, without changing driver binding or probing MMIO:

1. Exact board ID/model, `uname -r`, current `boot_id`, timestamp/source, active DTB hash where retrievable.
2. `/sys/class/uio/uio*/name`, `maps/mapN/addr,size,offset,name`, `device` and `device/driver` binding. `mapN` `mmap` selector is `N*PAGE_SIZE`, **not** physical base.
3. Relevant `/sys/bus/platform/devices/<name>/resource`, `driver` and `of_node/compatible`, FPGA Manager presence and current state.
4. Whether Kernel exposes FPGA Bridges/Regions and **whether they actually isolate PS↔PL transactions** on this exact PYNQ Z2 image. No generic-Linux-to-target inference.
5. Actual runtime users of relevant UIO and `/dev/mem` maps, kernel IP consumers and DMA: require PR #972's independent audited Guard or equivalent **before** a future live transition. A one-time inventory cannot close the race.
6. Existing original image (`base.bin`/HWH) full SHA, boot metadata, 100-MHz FCLK0 condition, external independent power/UART/SSH recovery operator observations; no fabricated attestation.

An initial offline inventory helper `python -m pl.tools.runtime_fpga_phase1 --contract pl/verification/runtime_fpga_abi_v1_proposal.json` is **strictly read-only** and outputs JSON to stdout. Its UIO resource mapping check deliberately does not claim a live hardware device from overlapping addresses. For initial board-specific evidence its output must be reviewed, not treated as an automatic HIL PASS.

## 4. Driver-Backend qualification order

| Stage | Software / Host | Real Z2 acceptance |
| --- | --- | --- |
| D0 | Contract and UIO sysfs fake-fixture tests | N/A |
| D1 | Driver Choice review; single 64-KiB UIO map vs per-Site maps; mapN selector and safe byte-offset rules | Read-only resource/driver evidence reviewed |
| D2 | Future UIOBackend with deterministic Device Discovery, exact u32 allowlists, ownership, generation invalidation and cleanup | UIO-01: exact mapping; UIO-02: approved Identity read; UIO-03: aligned u32; UIO-04: 2-Site separation; UIO-05: cleanup; UIO-06: conflict reject; UIO-07: reload exclusion |
| D3 | Failures: map disappeared, permission denied, UIO driver replaced, unexpected physical range, mapping size shrunk, duplicate match, fd closed but mapping retained | Any unknown/conflict -> NO-GO; never intentionally provoke invalid physical AXI transactions |

Driver HIL must use a **hardware-verified matching Bitstream**. Existing MS01 does not yet implement proposed v1 Identity/Site ABI.

## 5. Generic Supervisor host failure-injection obligations

Offline tests should cover these invariants before touching a physical FPGA:

- SUP-01 ready → quiesce → owner check → load → verify → ready.
- SUP-02 busy Site or uncommitted Job → load denied.
- SUP-03 leaked/inherited `/dev/mem` mmap (including after fd close) → denied.
- SUP-04 unknown active UIO/platform resource owner, deleted UIO mapping, malformed inventory → denied.
- SUP-05 hash/ABI/device tree mismatch → denied **before loading**.
- SUP-06 loader missing completion, exit failure or timeout → no false PASS.
- SUP-07 restoration or driver rebind failure → persistent FAULT.
- SUP-08 child crash/killed worker → no blind replay.
- SUP-09 supervisor crash/restart with Journal → reboot and process identity reconciled, no auto action if AXI status unknown.
- SUP-10 default dry-run is inert and never creates hardware-side effects.

**Critical hardware limitation:** even a robust Python supervisor can not necessarily interrupt an ARM AXI Stall or recover a crashed Kernel. External recovery is a mandatory independent contingency, not optional sugar.

## 6. Dynamic Bitstream A↔B qualification (Phase 4 real hardware; not now)

First design two distinct, separately signed/hashed **v1-compatible** FPGA Images with different capabilities and identical fixed Identity Register Layout. Confirm exact source SHA, manifest, BIT/HWH/BIN SHA, 32-bit address semantics, proper Clock/Reset and zero unintended external PL IO.

| Case | Required observed acceptance |
| --- | --- |
| SW-01 / SW-02 | A→B and B→A with no Linux reboot, correct image identity each time |
| SW-03 / SW-04 / SW-05 | Compatible Runtime Driver API, matching ABI Major, correct image Build ID and differing Capability |
| SW-06 / SW-07 | All Site jobs quiesced; old mapping generation invalid; exact new UIO sysfs physical maps and register allowlists qualified |
| SW-08 | SSH/Ethernet reachable before/after and observed during controlled switching from independent observer |
| SW-09 | Plasma Gateway reports `SWITCHING`, denies new programming requests, resumes only when qualified |
| SW-10 | Safe failure rollback and original bindings/metadata/services/image independently verified; failed physical recovery stays FAULT, no false PASS |
| SW-11 | `/proc/sys/kernel/random/boot_id` unchanged |
| SW-12 | Bounded repeated cycles with individual log, digest and no observed Kernel FPGA/AXI errors |

No HIL result is complete until an independently verified **restoration to the authorized baseline Image**, plus affected Kernel drivers, clock, services and health. A native worker's data PASS cannot substitute for that restoration.

## 7. Post-driver integration and later Site HIL

- Phase 5: Real two Site functional isolation, deterministic data and counter checks, Thread vs Process-IPC CPU / RAM / throughput / p95-p99 evidence. Process-IPC is not Process-Direct MMIO.
- Phase 6: Implement/measure Zynq-7010 8-Site capacity using actual LUT/FF/BRAM/timing; do not infer from Z2 Zynq-7020 or fake software Site count.
- Electrical HIL of Socket power, output-enable, pull-states, ground/reference and reset under PL reconfiguration must be separately passed before programming a real IC.
- Selected exact IC across one batch requires PPU-level admission validation; existing Site Desired settings are not sufficient evidence.

## 8. Acceptance state

**Phase 1 proposed artifacts can be ready for document/host-only review while Real Z2 remains NO-GO.** Promote ADR-0003 from Proposed to Accepted / M1 Freeze only after owner architectural decision, sufficient resource facts and qualification planning. Subsequent hardware phases require explicitly scoped Gate 1 authorization; this plan is not hardware authority.

No new approval Gate types: AGENTS.md §11 retains **Gate 1 Plan Approval** and **Gate 2 Merge Approval** only.
