# PLASMA Zynq-7020 Universal Fixed FPGA Image — Hardware ABI v1 / Gate 1

> **Status: REVIEW CANDIDATE, NOT ACCEPTED, NOT IMPLEMENTED IN RTL. M1 = NO-GO.**
> Machine-readable authoritative **proposal**: [`fixed_image_abi_v1_gate1.json`](../../pl/verification/fixed_image_abi_v1_gate1.json).
> This review has no live FPGA, MMIO, UIO, DUT, deployment, FPGA Manager or reload permission.
> A successful Host validator only establishes that the **proposal is internally consistent**.

## First-principle product invariant

The operator changes IC/profile/protocol while the **same running Linux / Ethernet / Gateway** remains up. v1 uses exactly one Universal **full fixed image** for normal programming; there is **no FPGA reload as part of a Job, batch transition, Site request, or protocol switch**. Boot-time/static provisioning and factory recovery are separate maintenance processes, outside this design's execution authority.

Development chip: **PYNQ-Z2 Zynq XC7Z020-1CLG400C**. A 7010 SKU is only a later cost candidate; do not size this first experiment from unmeasured 7010 capacity. The existing `base.bin`, LT02 and MS01 images do **not** implement these v1 registers.

The v1 proposed hardware transport is **32-bit little-endian, naturally aligned**, one PPU-wide candidate 64-KiB window. The actual physical base comes from a **reviewed Board Descriptor bound to the image and Kernel resource**, never from user-provided REST or from a hard-coded `/dev/uio0` path.

## Exact candidate aperture geometry (relative to Board Descriptor base)

| Window offset | Size | Ownership | Access |
| --- | --- | --- | --- |
| `+0x0000` | 4 KiB | PPU Identity / Capability | RO only |
| `+0x1000` | 4 KiB | Global health / event observation | RO only |
| `+0x2000`, `+0x3000` | 4 KiB each | Future shared engines | **RESERVED — do not access** |
| `+0x4000 .. +0xB000` | 4 KiB x 8 | Site 1..8 | Exact allowlist only |
| `+0xC000 .. +0xFFFF` | 16 KiB | Future expansion | **RESERVED — do not access** |

`site_base(site_id) = registered_base + 0x4000 + (site_id - 1) * 0x1000`. The **eight slots are architectural capacity**; `SITE_PRESENT_BITMAP` only reports RTL instances actually built and verified on the specific board. No fabricated physical Sites. `SITE_READY_BITMAP` alone cannot authorize programming.

### Global Identity (PPU base + byte offset)

`MAGIC 0x000 = 0x4D534C50` (`PLSM`), `ABI_VERSION 0x004 = 0x00010000`; `IMAGE_ID_W0..W3 +0x008..0x014` and `BUILD_ID_W0..W3 +0x018..0x024` are read-only identities. **Build ID is not a SHA256 substitute**; the manifest/loader receipt independently binds artifact source and bitstream digest.

`CAPABILITIES_LO +0x028`: bit 0=SWD; bit 1=SPI. JTAG/I2C/ICSP are reserved capability bit positions (2/3/4) **required to read zero in v1**; High capability word `+0x02C` is zero. `SITE_PRESENT_BITMAP +0x030`, `SITE_READY_BITMAP +0x034`, `PPU_STATUS +0x038`, `HW_REVISION +0x03C`, `PPU_ERROR +0x040`, `MAP_REVISION +0x044` (value 1), `SITE_STRIDE_BYTES +0x048` (4096), `MAX_TRANSFER_BITS +0x04C` (8–8192, byte-multiple), and `RESET_CAUSE +0x050` are read-only. Global health at `+0x1000` is observation only; it never grants power/reset/reload privileges.

### Per Site (all offsets relative to its 4-KiB window)

| Offset | Register | Access | Required semantics |
| --- | --- | --- | --- |
| `0x000–0x010` | SITE_ID, SITE_ABI_VERSION, SITE_CAPABILITIES, SITE_STATUS, SITE_ERROR | RO | Identity, readiness, latched fault |
| `0x014–0x01C` | INFLIGHT_SEQ, RX_WORDS_AVAILABLE, TX_WORDS_FREE | RO | Hardware bounded outstanding seq and FIFO counts |
| `0x020–0x03C` | COMMAND, SEQUENCE, PROTOCOL, FLAGS, BIT_COUNT, ARG0, WDATA, TIMEOUT_TICKS | WO | Explicit bounded request fields; write COMMAND **last** |
| `0x040`, `0x044` | TX_DATA, RX_DATA | WO / RO | PIO FIFO push/pop, 32-bit little-endian bytes |
| `0x048–0x050` | DONE_SEQ, DONE_STATUS, DONE_WORDS | RO | Completion must echo exact sequence; terminal result explicit |
| `0x054` | ABORT | WO | Write 1 requests Site abort, **not** guaranteed bus cancellation |
| `0x058` | CAPACITY_WORDS | RO | 1–256; real depth must be measured, no assumed BRAM |
| `0x05C` | CLOCK_DIV | WO | Bounded integer 1–65535, only while IDLE |
| `0x060` | DONE_DATA | RO | SWD read 32-bit result on successful completion |
| `0x064` | ACK_SEQ | WO | Only exact DONE_SEQ releases terminal result to IDLE |
| `0x068` | TRANSACTION_COUNTER | RO | Diagnostics only, wraps; not durable identity |

These are proposed **wire contracts**, NOT safe speculative offsets for the current FPGA! No read-modify-write and no access outside the approved RO/WO sets. All slots must return defined AXI responses; malformed requests should be rejected by **software prior to issuing an AXI transaction**. Whether RTL can fail safely for arbitrary accesses remains an independent hardware verification task.

## Command protocol (proposed minimum complete v1 PIO subset)

1. Broker checks current Board Descriptor, bitstream receipt, UIO binding/physical map, PPU image Identity, exact Site identity, ABI major, capability bits, one active Site lease, same exact IC across the active batch, and independently qualified Site Power/Reset.
2. Exactly **one outstanding command per Site**. Only an IDLE Site can accept a new command. A Site's sequence ID is a nonzero 32-bit value and must not be reused while pending. The broker tracks a separate boot/owner/mapping generation to prevent stale completion or sequence wrap becoming a new command.
3. Set `SEQUENCE`, `PROTOCOL`, `FLAGS`, `BIT_COUNT`, `ARG0`, `WDATA`, `TIMEOUT_TICKS`, `CLOCK_DIV` and fill `TX_DATA` as required. Enforce the real FIFO depth and Board Descriptor timing policy. Apply the platform-qualified **device MMIO ordering barrier** before committing `COMMAND`; Python Host contract merely emits a `BARRIER_REQUIRED` marker, not a real barrier.
4. Commands: `SWD_XFER=1` (protocol SWD=1, 32 data bits, ARG0 bit0 APnDP / bit1 RnW / bits2–3 A2/A3), `SWD_LINE_RESET=2` (50..128 logical-high cycles), `SPI_TRANSFER=3` (protocol SPI=2, 8..MAX_TRANSFER_BITS byte-multiple, full-duplex FIFO, CS0..3 from ARG0, FLAGS bit0 CS_HOLD). SWD request parity/turnaround is engine behavior to qualify; SWD WAIT/FAULT is an explicit completion class, **not** permission to replay an uncertain write.
5. `SITE_STATUS`: exactly one of `IDLE=1`, `BUSY=2`, `DONE=4`, `FAULT=8`; `DONE_SEQ` must match submission. `DONE_STATUS` is one of `OK=0`, `SWD_WAIT=1`, `SWD_FAULT=2`, `SWD_NO_ACK=3`, `PARITY=4`, `TIMEOUT=5`, `ABORTED=6`, `BAD_ARGUMENT=7`, `ENGINE_UNAVAILABLE=8`, `INTERNAL_FAULT=9`. Collect DONE_DATA/PIO RX and then acknowledge exact `ACK_SEQ`. Never auto-replay a transaction whose effect is ambiguous.
6. SPI packing: bytes in ascending least-significant byte lane of TX_DATA/RX_DATA, final high unused bits must be 0; `ceil(BIT_COUNT/32)` TX words; no silent FIFO overflow or out-of-order inter-site results. `MAX_TRANSFER_BITS` and `CAPACITY_WORDS` must be read from qualified hardware and jointly limit admission.
7. Timeout/abort is only a **control-plane intention**. It cannot prove that AXI requests drained or that an ARM process escaped a Kernel/AXI hang. Any ambiguous state faults the Site and blocks unattended retry. `ACK_SEQ` cannot erase `FAULT` without an independent validated recovery procedure.

**v1 deliberately excludes DMA, IRQ, JTAG, I2C, ICSP, FPGA Image switching, PL-owned DUT power/reset.** Their reserved capability codes are not functionality. Future additions require a new reviewed ABI version and resource/timing evidence. The first v1 minimum profiles are SWD and SPI only; whether one XC7Z020 fixed image can implement both engines across physical Sites requires LUT/FF/BRAM/TIMING/HIL evidence.

## Concurrent Site and separation invariants

One PPU = one current Image, one **Hardware Broker**, one exact-IC-per-batch, up to eight independently admitted Site leases, at most one in-flight transaction per Site. Unique per-DUT serial/image/calibration content remains valid. Hardware may share protocol-engine resources internally, but an internal shared engine may NOT corrupt other Site state; scheduling/fairness/latency must be measured. Per-Site Job cancellation and a shared PPU-wide abort are distinct.

Site control must not directly own DUT Power/OE/Reset: existing `SiteSafetySequencer` and separately designed out-of-PL electrical circuitry must establish safe-off/connect-under-reset semantics. No claim that PYNQ-Z2 already has those circuits.

## M1 freeze versus real hardware

**M1 architecture acceptance requires** a peer-reviewed immutable ABI, complete transaction semantics, board-specific resource resolution, Owner/Broker lock/admission design, specified recovery/power boundary, hostile Host tests, and an explicit Owner architectural decision. Hardware HIL/RTL acceptance is a **separate** stage; M1 alone cannot authorize a live UIO driver, physical eight Sites, or a programming Job.

Before declaring this proposal Accepted: RTL owner must review bus register side effects, FIFO capacity, memory ordering, AXI-Lite response, clock/reset and BRAM budget, plus distinguish how FIXED Image is provisioned from unsafe runtime reload. Until that review, **M1 = NO-GO, ABI = REVIEW CANDIDATE**.

Test: `python3 -m pytest -q pl/tests/test_fixed_image_abi_contract.py`.
