# ADR-0003 — PPU Runtime FPGA Driver and Reconfiguration Boundary

> **Status: Proposed (amended fixed-image v1 Gate 1 candidate)** — **not Accepted**, M1 NO-GO. Original dynamic-switching content retained below as deferred research.
>
> **Date:** 2026-10-16. **Related:** [Runtime FPGA Architecture v1.0 roadmap](../architecture/runtime-fpga-architecture-v1.md), [Proposed Hardware ABI v1](../architecture/runtime-fpga-hardware-abi-v1.md), [Switching/HIL plan](../development/runtime-fpga-switching-hil-plan-v1.md).
>
> **Authorization:** documentation and host-only analysis. No live FPGA load, unbind, physical MMIO, deployment, firmware updates, HIL-B/C or merge is authorized by this proposal.

## 2026-10-17 Gate 1 amendment — first-generation Universal **Fixed** Image (normative candidate)

**Decision status: PROPOSED / owner M1 review required.** This amends the prior *candidate* runtime-reconfiguration roadmap without claiming that ADR-0003 is Accepted, M1 frozen, or any RTL/real UIO implementation complete. For first-generation normal programming, **a single fixed Universal FPGA image is the product baseline** on development PYNQ-Z2 **XC7Z020 (Zynq-7020)**. Future Zynq-7010 cost-down remains a measured option, not a present FPGA resource constraint.

**Product requirement vs mechanism:** switching exact target IC and SWD/SPI supported protocol must not reboot PS/Linux/Ethernet/Gateway. A Profile/Algorithm/Engine selection within one image satisfies this; **runtime bitstream A/B reload is not required for first-generation normal Jobs**. Every normal FPGA Manager firmware/reload operation, driver unbind/rebind, and direct Worker/REST image-load path is excluded by design. Boot-time provisioning and maintenance recovery are separate future safety/authorization flows. If measured Zynq-7020 timing, FF/LUT/BRAM or 2→8 throughput makes one Universal Image infeasible, reopen dynamic switching as a distinct ADR/M1 redesign and independently qualify K0..K5; do not silently enable the old proposal's reload fallback.

**Gate 1 deliverable sources:**

- [First-generation **full minimum SWD/SPI PIO** ABI v1 review candidate](../architecture/fixed-fpga-hardware-abi-v1-gate1.md) and [machine-readable JSON](../../pl/verification/fixed_image_abi_v1_gate1.json) define PPU Identity/Capabilities, Site 1–8, Sequence/Command/Response/FIFO/Timeout/Abort/Acknowledge, reserved offsets, endianness and versioning. JTAG/I2C/ICSP, IRQ and DMA are explicitly unsupported in this candidate v1 pending measured scope, not silently claimed implemented.
- [UIO Driver admission and mapping contract](../development/fixed-fpga-uio-driver-contract-gate1.md) chooses **one 64-KiB PPU UIO map0 as preferred PoC candidate**, not as an unconditional production decision. Match Driver/DT/physical resource and unique UIO identity, not `/dev/uio0`. Host `uio_backend.py` remains ordinary-file-only; real `/dev/uio*` has **not** been enabled or tested by this work.
- [Single privileged Hardware Broker and eight-Site ownership](../architecture/fixed-fpga-hardware-broker-eight-site-gate1.md) separates logical Batch Execution Owner, MMIO hardware owner, per-Site Transaction leases and independent Site Power/Reset/OE safety owner. One Batch exact IC across all admitted Sites; per-DUT data/status/results remain separate. Old in-memory Site lease/advisory `flock` do not provide Kernel-enforced noncooperating/DMA exclusivity.
- [Host-only ABI/Mapping/Admission validator](../../pl/tools/fixed_image_abi_contract.py) rejects a mis-stated implementation status, runtime reload, fabricated eight physical Sites, wrong ABI/offsets, ambiguous UIO/resource, stale owner/lease/generation, unsupported capability and malformed SWD/SPI transactions. Its output is an **offline proposal review**, not an FPGA Readback, a production Driver, or access authorization.

**What prior sections below mean after amendment:** references to FPGA Manager/Bridge, general-purpose runtime reload, A/B images, and future custom Kernel Driver are **deferred architecture alternatives or eventual maintenance/upgrade requirements**, not current first-generation normal-programming obligations. The prior proposed dynamic Image Switching path is superseded for the v1 runtime requirement. Retain its technical hazard and K0..K5 reasoning as independent evidence for any *future* loader plan.

**M1 Freeze acceptance for the revised v1 scope:** explicit owner-reviewed ABI and data-plane control semantics; independently reviewed Zynq-7020 Board Descriptor, fixed-image provisioning policy and silicon capacity budget; UIO-versus-Kernel Driver decision with non-cooperative access risk assigned; single Broker/8 Site concurrency/Exact IC and IO-safe ownership specification; all Host-only source/checker/negative tests passing; RTL/PS owners sign off on ordering/FIFO/resource feasibility. Only then may ADR-0003 transition Proposed→Accepted through separately approved Gate 2; **physical MMIO, FPGA reload, eight-Site performance, and product/HIL qualification remain separately gated**.

**Current verdict: M1 = NO-GO / ABI v1 = REVIEW CANDIDATE / hardware execution = NOT AUTHORIZED.**

## Context / non-negotiable requirements

1. A PPU owns one active FPGA configuration shared by Sites 1–N (future target: eight). A batch targets one exact IC type; Site payload, programming progress and recovery remain independent.
2. A change of Target IC/interface MUST NOT require Linux/PPU reboot. Reconfigure algorithms or a universal engine first; when hardware capability differs, switch a compatible image at runtime with all Site jobs quiesced.
3. Ethernet, SSH, Plasma Gateway and Linux remain alive across normal interface switching. `SWITCHING` is a temporary admission-denied state, not a completed programming job.
4. One **configuration owner** coordinates FPGA Manager, MMIO mappings, kernel-bound consumers and independent recovery. This is distinct from the existing [PPU execution-owner lease](../architecture/ppu-execution-ownership.md), which is a logical Job admission policy.
5. The Board Power/Reset/Electrical-safe state must not rely solely on the PL logic being reconfigured. External DUT safety needs a separate circuit/HIL qualification.

## Observed implementation facts (NOT an architecture decision)

- `software/python/plasma_interfaces/linux_mmio.py`: native ARMv7 32-bit `memoryview('I')`, `/dev/mem`, immutable per-aperture RO/WO allowlists, advisory `flock` and Site leases. It is not a Linux kernel driver, cannot provide exclusive hardware capability against privileged/non-cooperating consumers, and does **not** control FPGA reload.
- `software/python/plasma_interfaces/fpga.py`: `FPGAInterface` raises `INTERFACE_NOT_CONFIGURED`; it is **not** a ready FPGA programming driver.
- `docs/architecture/ppu-site-configuration.md`: per-Site desired `interface`/`target` persistence is implemented; hot-apply and physical FPGA qualification are **not**. New same-IC-per-batch admission must later be specified and enforced at a PPU batch boundary, not faked by renaming Site fields.
- PR #972 (unmerged): six 4-KiB PL apertures; its Fabric UIO read-only HIL-A found a 64-KiB kernel UIO mapping (`0x40000000–0x4000FFFF`). B2 retained-map Guard and B3 Supervisor Host-only tests PASS, B1 live ownership and actual MS01 HIL-B/C remain NO-GO.
- Previously proven 5-aperture original `base.bin` restore does **not** qualify the six-aperture image or future ABI.
- **Missing physical evidence:** exact current kernel/DTB/FPGA bridge paths, all UIO map names/offsets, active consumers, UART/power recovery, and safe Bridge behavior under full reconfiguration. The [read-only inventory collector](../../pl/tools/runtime_fpga_phase1.py) generates candidate observations but cannot prove there are no racing hardware consumers.

## Proposed decision (conditional; requires architecture review and M1)

**A. Programming/board-management interface: stable semantic HW API, not an exposed raw MMIO address in UI or OpenOCD.**

~~~text
SiteWorker / OpenOCD Plasma Adapter   Board / Recovery Supervisor
                 \                    /
                  Plasma HW API (semantic)
                           |
                   PPU Hardware Manager
                  /                  \
        Runtime MMIO Backend       FPGA Lifecycle Supervisor
      UIO (candidate) / devmem     FPGA Manager/Bridge (if qualified)
                  \                  /
                         AXI GP0 / PL
~~~

The FPGA configuration owner is unique at PPU level. A single Runtime Service should control MMIO; Site-specific leases are not separate FPGA configuration owners. Read32/write32 are **internal implementation primitives**, not remote user APIs.

**B. Driver PoC ranking: evaluate UIO first, retain bounded DevMem for development; do not yet require a custom kernel driver.**

| Alternative | Candidate fit | Important limitation | Phase 2 disposition |
| --- | --- | --- | --- |
| `/dev/mem` native `mmap` | Existing qualified prototype transport; useful differential and recovery tests | Bypasses device-specific resource ownership; `flock` advisory; unsafe to assume exclusive access | Retain in controlled lab only |
| `/dev/uioX` (`uio_pdrv_genirq` where appropriate) | Minimal Kernel resource declaration, userspace u32 MMIO, future IRQ option | Any permitted process may map UIO; not a Kernel-enforced Site ACL. No automatic reload/quiesce/recovery protection | **Preferred first experimental Backend**, pending Kernel/DT evidence and controlled HIL |
| Custom Kernel Driver | Can enforce a single accessor and own IRQ/DMA/bridge transactions | Maintenance, safety and qualified ARMv7 build burden | Consider if UIO cannot meet non-cooperative isolation, robust DMA/IRQ or image-transition requirements |

An existing broad UIO map is **not** proof of active MMIO bus transactions. Unbinding it is **not** equivalent to PS-to-PL physical isolation. First inspect sysfs and the actual driver consumers, then create an explicit, reviewed device lifecycle.

**C. One full PPU UIO map is the initial candidate, not a hard product requirement.** The observed 64-KiB region could host PPU-level ABI + up to eight 4-KiB Site slots if the **hardware RTL/DT contract is deliberately aligned**. Separate UIO objects per Site require additional DT resources and complicate image lifecycle; they do **not** inherently grant race-free multi-process ownership. Decide after verifying physical Kernel mapping and future IRQ/DMA needs.

**D. UIO mapping semantics must be explicit.** In Linux UIO, `mmap(fd, offset=N*PAGE_SIZE)` chooses `mapN`, **not** physical address `N*PAGE_SIZE`. The relevant physical start/size/byte-offset come from `/sys/class/uio/uioX/maps/mapN/{addr,size,offset}`. When one 64-KiB `map0` covers many ABI windows, userspace maps `map0` once and uses checked window-relative offsets. Do not attempt `mmap(/dev/uioX, 0x40004000)` as for `/dev/mem`.

**E. FPGA Manager/Region/Bridge remain separate from Runtime MMIO.** Runtime Backend has no FPGA-load permission. A Board Supervisor manages preflight, quiesce, explicit owner reconciliation, image identity, load, ABI handshake, safe recovery, and external AXI-stall escalation. Kernel `fpga_region` and `fpga_bridge` are only usable where the actual target Kernel, DTB and PS–PL fabric expose and validate them.

**F. Same-IC-per-batch is a domain migration requirement, not yet current enforcement.** Existing per-Site `target/interface` Desired fields remain until separate admission/backend work reconciles PPU-level selected target/profile with Site-level execution and per-DUT data. Do not silently alter current API/schema in Phase 1.

## Alternatives and trade-offs

- **Always reload on IC change:** rejected, unnecessary when algorithm changes inside one hardware protocol; increases maintenance risk.
- **Always reboot for protocol change:** rejected by product requirement.
- **Custom kernel driver immediately:** deferred; without proven hard requirements, development cost is unjustified.
- **Reuse PYNQ `base.bin` ABI as PLASMA ABI:** rejected; Base Overlay hardware layout is different.
- **Treat LT02/MS01 5-/6-aperture image as ABI v1:** rejected; these are HIL fixtures with different registered semantics, not v1 product qualification.
- **Permit reconfiguration with open UIO mappings:** rejected absent a separately proven, platform-specific safe protocol; driver binding and mmaps do not automatically become valid when PL logic changes.

## Evidence to resolve before Accepted/M1

- [ ] Fresh *read-only* actual Z2 Kernel/DTB, Platform Devices, `uio* maps`, driver binding, bridge/FPGA Manager snapshot; hardware-provenance/date/boot ID.
- [ ] Compare one PPU UIO mapping vs per-Site maps at 2/8 Site, with correct UIO `mapN` selector behavior.
- [ ] Review and freeze [Proposed Hardware ABI v1](../architecture/runtime-fpga-hardware-abi-v1.md) with RTL and PS owners, including image A/B compatibility and unsafe accesses.
- [ ] Establish reconfiguration mutual exclusion beyond advisory userspace lock: identify known Kernel/Userspace consumers, operating system permissions, safe-state and fail-closed policy.
- [ ] Confirm actual Z2 FPGA Bridge/PS–PL isolation support (or document alternative with real hardware risk); no assumption from upstream docs.
- [ ] Separate gate-controlled Phase 2 Driver HIL and Phase 4 A/B Switching HIL; retain independent recovery and no-reboot observations.
- [ ] Demonstrate agreed hardware ABI actually emitted by a new FPGA image before promoting it to a **Current** contract.

**Interim engineering decision:** UIO is the *preferred PoC direction*, not an accepted product Driver or physical qualification.

## References

- [Linux kernel UIO HOWTO](https://docs.kernel.org/driver-api/uio-howto.html) (UIO sysfs mapping, `mapN` selector).
- [Linux kernel FPGA Region](https://docs.kernel.org/driver-api/fpga/fpga-region.html) (Manager, Bridge and region dependency).
- [Linux FPGA programming API](https://docs.kernel.org/driver-api/fpga/fpga-programming.html).
