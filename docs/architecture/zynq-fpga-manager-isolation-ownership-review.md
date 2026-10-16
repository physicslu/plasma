# Zynq FPGA Manager isolation and runtime ownership review

> **Status: Host-only review, 2026-10-17. M1 architecture freeze: NO-GO.**
> This is an evidence ledger and a proposed ownership contract, not an accepted
> hardware ABI, a board reload procedure, or authorization for HIL-B/C. It
> reviews [ADR-0003](../adr/0003-runtime-fpga-driver-reconfiguration-boundary.md),
> the [proposed ABI v1](runtime-fpga-hardware-abi-v1.md), and [Issue #975](https://github.com/physicslu/plasma/issues/975).

The product requirement remains: selecting another exact IC or programming
interface must not reboot Linux, SSH, Ethernet, or Plasma Gateway. An algorithm
or profile change that the active image can perform should avoid FPGA reload.
A change that truly needs a different image requires one PPU configuration
owner, all-Site quiescence, physical transition safety, independent recovery,
and new-image admission before jobs resume. The present Z2 evidence does not
establish that transition boundary.

## Evidence and source provenance

The private, raw command/exit/stdout/stderr records and SHA-256 manifest are
retained on SWPC under `.work/issue977-evidence/20261016T160635Z/`. The
earlier read-only Z2 inventory and verified manifest remain under
`.work/issue975/20261016T154641Z/`. No private target endpoint, credentials,
or operator data are published here. `sha256sum -c` passed for the earlier
inventory before this review cited it. The review branch starts from
`main` commit `3a54c30b0e171cf55dcc52fbc366b657c4c3d0c0`.

| Class | Observation or source | Consequence |
| --- | --- | --- |
| VERIFIED, actual target | ARMv7 `6.6.10-xilinx-v2024.1-g3c0eca68c652`, PynqLinux 3.0, boot-matched `/proc/config.gz` SHA-256 `842cd4d4f17487123ca33c7b04f593dc85340df11da59c2059ccc12b699a5169`; `CONFIG_FPGA_MGR_ZYNQ_FPGA=y`, `CONFIG_FPGA_MGR_ZYNQ_AFI_FPGA=y`, `CONFIG_FPGA_BRIDGE=y`, `CONFIG_OF_FPGA_REGION=y`, `CONFIG_UIO_PDRV_GENIRQ=m`. | Feature compilation is known; it does not prove that a bridge or AFI device is instantiated. |
| VERIFIED, actual target | Manager `fpga0` resolves to `/sys/devices/soc0/axi/f8007000.devcfg`, bound driver `zynq_fpga_manager`, DT compatible `xlnx,zynq-devcfg-1.0`; devcfg has a `syscon` phandle and an SLCR node exists. Region `region0` is bound to `of-fpga-region`; the active region DT node has `fpga-mgr` but no `fpga-bridges`. `/sys/class/fpga_bridge` is empty. | Manager and region exist, but no registered bridge was observed. A region object is not proof of bus isolation. |
| VERIFIED, actual target | `/dev/uio0` (`fabric`) has one `map0`: physical `0x40000000`, size `0x10000`, byte offset zero, bound `uio_pdrv_genirq`. FCLK0 was 100 MHz. The last Kernel load record in the same boot named `base.bin`; manager state was `operating`. | One UIO mapping can address the proposed 64-KiB window, but `base.bin` does not implement ABI v1. `operating` is not a provenance or quiescence certificate. |
| VERIFIED, snapshot only | Issue #975's root scan read all 91 then-existing `/proc/PID/maps` and fd directories without denial and found no `/dev/mem` or UIO handle/VMA. | No relevant user-space consumer was observed **at that instant**; a new or inherited mapping can race it. No AXI access was made. |
| VERIFIED, local software | Current `LinuxMMIO` uses `/dev/mem`, an advisory global `flock`, per-Site leases, and `quiesce_for_reload()` that rejects active in-process leases. [Source](../../software/python/plasma_interfaces/linux_mmio.py). Independent unmerged [PR #972](https://github.com/physicslu/plasma/pull/972), head `e9ac002480f53dc89a95d71990f6757b2f6a69b9`, has Host-only six-aperture retained-VMA guard and journaled default-dry-run supervisor. | Neither the advisory lock nor a cleared in-process lease excludes non-cooperating privileged code, a Kernel IP driver, DMA, or all outstanding AXI transactions. PR #972 B1 live handoff remains BLOCKED and HIL-B/C NOT RUN. |
| SUPPORTED_REFERENCE, **not a matching target source** | Xilinx `linux-xlnx` tag `xilinx-v2024.1` resolves to commit [`e475cc1c9432587298212570c2af2be66b820c41`](https://github.com/Xilinx/linux-xlnx/tree/e475cc1c9432587298212570c2af2be66b820c41). Its [Zynq manager](https://github.com/Xilinx/linux-xlnx/blob/e475cc1c9432587298212570c2af2be66b820c41/drivers/fpga/zynq-fpga.c) full-load path asserts SLCR FPGA AXI resets, changes level shifters, configures PCAP/DMA, then enables PL-to-PS shifters and deasserts resets after completion. Its [region](https://github.com/Xilinx/linux-xlnx/blob/e475cc1c9432587298212570c2af2be66b820c41/drivers/fpga/fpga-region.c) uses a bridge list and manager lock; its [DT region layer](https://github.com/Xilinx/linux-xlnx/blob/e475cc1c9432587298212570c2af2be66b820c41/drivers/fpga/of-fpga-region.c) accepts an empty bridge list. | This explains a plausible load path, **not** the code proven to run on this board. The reference enables the PS-to-PL direction during full configuration; none of these source operations alone proves that pre-existing or racing AXI requests drain safely. |
| UNKNOWN, source lineage | The target's Kernel build string contains `g3c0eca68c652`, but the Xilinx public repository commit lookup for that prefix returned “No commit found”; the installed Kernel build tree contains config/headers but no `drivers/fpga/zynq-fpga.c`. No matching vendor patch set or source-to-binary attestation was found. | Do not promote the 2024.1 reference's specific reset, error, or lock behavior to a verified property of this Kernel. Obtain its exact PetaLinux source/patch provenance before physical isolation claims. |
| UNKNOWN, physical behavior | No bridge device, bus-drain proof, AXI-stall containment result, live Kernel/DMA consumer audit, exact PL ABI readback, or future MYIR Zynq-7010 resource map was established. | Full-load safety, eight-Site capacity, and generic-image switching remain unqualified. |

The Xilinx reference [manager core](https://github.com/Xilinx/linux-xlnx/blob/e475cc1c9432587298212570c2af2be66b820c41/drivers/fpga/fpga-mgr.c)
has a direct `firmware_store` → firmware-load path with no explicit region
bridge-list operation in that function. Region programming is a separate API.
The target's historical loads used the Manager firmware sysfs path, so a
region's mere registration must not be credited with gating those loads.
Whether this exact target build has equivalent code is still UNKNOWN. The
[Linux FPGA programming API](https://docs.kernel.org/driver-api/fpga/fpga-programming.html)
describes bridge disable/re-enable as part of a **region** programming call;
it does not confer that behavior on every Manager sysfs write.

## Ownership layers and non-equivalences

| Layer | What can be asserted now | What it cannot establish |
| --- | --- | --- |
| Kernel binding/resource | Fabric UIO claims a single 64-KiB map. The devcfg Manager and region drivers are bound. | Binding is not active MMIO traffic, an exclusive capability, or PS–PL isolation. A driver unbind is not a bus-drain primitive. |
| UIO map | `map0` begins at physical `0x40000000`, `size=0x10000`, `offset=0`; the UIO `mmap()` file selector is `0`, **not** `0x40000000`. For `mapN`, selector is `N × page_size`, with `mapN/addr,size,offset` checked separately. [Kernel UIO HOWTO](https://docs.kernel.org/6.6/driver-api/uio-howto.html). | One broad map does not grant per-Site hardware ACLs; a closed fd can leave a VMA alive. |
| Process/VMA | A privileged scan can detect known `/dev/mem` physical-offset overlaps and UIO fd/VMA users, including retained maps; PR #972 Host tests cover its guard. | A snapshot is not atomic with another process's `open`/`mmap`, and `/proc` does not certify Kernel DMA inactivity. Unknown/denied observations must fail closed. |
| Cooperative runtime | The existing `LinuxMMIO` lock and Site leases coordinate cooperating callers within the present driver. A future PPU configuration owner must prevent new Gateway/worker admissions before any audit. | Advisory `flock` does not prevent another privileged process or Kernel driver from touching PL. |
| Kernel/physical fabric | The reference manager can reset AXI interfaces and change shifters as part of a load; no live target bridge is enumerated. | No proof that an outstanding PS→PL transaction completes, aborts safely, or can be interrupted by a Python timeout. No independent external DUT safe-state is proven. |

PR #972's Host supervisor remains a useful *candidate mechanism*: it seals
candidate/recovery hashes, journals intent, audits six apertures, preserves
bindings, and leaves AXI-unknown failures for external recovery. It does not
grant this review authority to unbind a live UIO device or load its image.
Before any later load, B1 requires a fresh, serialized ownership handoff that
includes retained VMAs and all relevant Kernel/PL consumers. B2/B3 Host PASS
does not close B1.

| Failure mode | Required response before later hardware admission |
| --- | --- |
| New UIO or `/dev/mem` mapping races a completed `/proc` scan | Close Job admission first; hold a single configuration authority and re-audit at the release boundary. Unknown process or retained VMA blocks load. |
| UIO driver unbound while another process retains a mapping | Treat the mapping as live until independently released; unbind alone cannot authorize reload. |
| Kernel DMA or PL IP continues beyond Site lease release | Stop and verify each registered consumer; unsupported or unenumerated consumer is NO-GO. |
| Reset or level shifter asserted with outstanding AXI | Do not claim drain from a register write or software timeout. Qualify isolation and external recovery before full reload. |
| Candidate load returns success but image/ABI/readback differs | Deny jobs; record fault and use only the qualified restoration path. |
| Worker, supervisor, or Kernel stalls mid-transition | Preserve journal, withhold new mapping generation; unresolved AXI state requires external recovery, never blind retry. |

## Proposed PPU configuration owner contract

This is a review contract for later implementation, not a new runtime API.
There is **one PPU-level Configuration Owner** over image selection and mapping
generations. It is distinct from the logical Batch/Normalized-Image execution
owner and from each Site lease. A batch admits one exact IC/profile across all
Sites; per-Site payload, serial data, result, and cancellation remain separate.
An isolated OpenOCD worker uses a Site lease through the PPU hardware API; it
cannot control FPGA Manager, bypass quiesce, or retain a valid map across an
image generation change. Board-management/recovery authority is separate
from workers and must remain reachable when Site execution fails.

```text
IDLE -> QUIESCE -> OWNERSHIP_AUDIT -> SAFE_IO -> RELEASE
     -> FPGA_LOAD -> VERIFY -> NEW_MAPPING_GENERATION -> READY
                 \---------------- failure ----------------> FAULT
       AXI completion unknown / hung Kernel -> EXTERNAL_RECOVERY_REQUIRED
```

1. `IDLE`: stable, admitted image and known generation. Gateway exposes actual
   state. Profile-only changes supported by this image retain it.
2. `QUIESCE`: deny new Gateway/Batch/OpenOCD jobs, wait for all Sites idle and
   terminal results, stop relevant DMA and asynchronous workers, revoke Site
   leases. Busy or uncommitted work rejects transition.
3. `OWNERSHIP_AUDIT`: hold the sole configuration authority, compare live
   Kernel bindings, `/proc` fd/VMA including inherited/retained maps, UIO
   physical ranges and driver identities with a reviewed allowlist. An unknown
   owner, changed boot/map, or audit race is NO-GO. An advisory userspace lock
   can coordinate known processes but is not the entire exclusion boundary.
4. `SAFE_IO`: establish an independently specified external-pin/DUT safe
   state and reviewed PS–PL isolation or equivalent hardware-safe procedure.
   **This step is currently unqualified and blocks live switching.** Never
   assume a manager lock, UIO unbind, reset bit, or timeout supplies it.
5. `RELEASE`: close/unmap the old generation, verify no retained VMA or DMA,
   and preserve original binding/recovery metadata before any authorized
   unbind. Failed release enters `FAULT` without a load.
6. `FPGA_LOAD`: only the configuration owner may request a separately
   authorized, hash-pinned image. Journal intent and current boot. A failed
   or ambiguous load cannot become `READY` from a return code alone.
7. `VERIFY`: independently read permitted new-image Identity/Build ID/ABI,
   exact UIO/DT resources, clock, Kernel/service health, and restore path.
   Any mismatch leaves admission closed and uses a separately qualified
   recovery procedure when AXI safety is known.
8. `NEW_MAPPING_GENERATION`: issue fresh driver mappings and Site leases;
   every pre-load handle is invalid. `READY` follows only complete admission.

`FAULT` preserves the journal and denies programming. A child crash or load
failure permits only the recovery path proven safe for that failure class. A
possible stalled ARM AXI access, hung Kernel, or unknown bus state goes to
`EXTERNAL_RECOVERY_REQUIRED`; no automatic retry, timed-out Python worker, or
blind FPGA reload can be claimed to repair it. Independent power/UART/SSH
recovery remains a separate qualification, not an every-run attestation.

## ABI/topology review and M1 decision

The proposed 64-KiB UIO map can fit Identity at `+0x0000` and Site 1–8 at
`+0x4000` through `+0xB000`, but an address fit is not ABI implementation.
`base.bin`, LT02, and MS01 do not implement the proposed v1 register meanings.
Keep `proposed_not_implemented` and reserve the unspecified control/shared
slots; do not probe them. One `map0` is the simplest Z2 PoC candidate. Per-Site
UIO objects require new DT/RTL resource ownership and still do not create
race-free multi-process isolation. A custom Kernel driver becomes a justified
alternative only if requirements such as enforced non-cooperating exclusivity,
IRQ/DMA ownership, or robust image transition cannot be met with UIO plus an
independent configuration owner. The MYIR Zynq-7010 base address, resources,
clock, LUT/BRAM budget, and physical Site count require separate measurements;
eight slots in a JSON proposal are capacity, not inventory.

**M1 = NO-GO.** The evidence supports further UIO-first Host design, not an
Accepted ADR or physical A/B transition. Blocking facts are: unmatched target
Kernel source/patch lineage, no demonstrated PS–PL bus isolation/drain,
unclosed B1 live handoff, absent ABI-v1 hardware images and independent
image/readback acceptance. None can be replaced by Issue #975's snapshot or
PR #972's Host-only PASS.

The next explicit Gate 1 scope should implement a **Host-only Phase 2**:
UIOBackend discovery/mapN and aligned-u32 allowlists; mapping-generation and
lease invalidation; concurrent Job/worker/DMA/unknown-owner rejection;
retained-fd-closed VMA and source/DT mismatch fault injection; and a reviewer
decision on one-map versus per-Site topology. A later, separately scoped Z2
HIL plan must obtain exact Kernel source/patch provenance or conservatively
review binary behavior, qualify physical isolation and independent recovery,
build actual ABI-v1 image(s), then measure controlled load/restore without
reboot. No Phase 2 implementation, target MMIO, FPGA load, service change,
or PR #972 modification was performed in this review.
