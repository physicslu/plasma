# OPP FPGA Register Map v1 — new ABI, four Site windows (Gate 1)

Status: **candidate, source-only**. This is a breaking new design, not a deployed image or a claim of four implemented SWD engines. No legacy SWD-v5 register offsets, driver allowlists or compatibility shim are inherited.

## Addressing and ownership

All offsets below are relative to **one FPGA image MMIO aperture**. The actual PS physical base, Device Tree resource and AXI interconnect decode are not assigned here; they require a reviewed board-specific integration. Never access these proposed addresses on Z2.

| Region | Relative byte offsets | Size | Owner |
| --- | --- | --- | --- |
| Global common registers | 0x0000–0x0FFF | 4 KiB | One instance per FPGA image |
| SWD Site 1 | 0x1000–0x1FFF | 4 KiB | Site 1 independent engine, reserved |
| SWD Site 2 | 0x2000–0x2FFF | 4 KiB | Site 2 independent engine, reserved |
| SWD Site 3 | 0x3000–0x3FFF | 4 KiB | Site 3 independent engine, reserved |
| SWD Site 4 | 0x4000–0x4FFF | 4 KiB | Site 4 independent engine, reserved |
| Future expansion | 0x5000–0xFFFF | 44 KiB | Not implemented; reject accesses |

Site window formula: `site_offset(n) = 0x1000 * n`, n=1..4. Each Site window is **reserved, not populated** until its SWD register contract and engine exist. No aliasing of unimplemented Sites to Site 1, no implicit multiplexing or shared Site FSM. Software must not probe reserved windows to detect hardware.

## Global registers (32-bit aligned, little-endian)

| Offset | Register | Access | Meaning |
| --- | --- | --- | --- |
| 0x000 | MAGIC | RO | 0x4D534C50 (`PLSM` little endian) |
| 0x004 | ABI_VERSION | RO | Major:16 / Minor:16; initial 0x00010000 |
| 0x008–0x014 | IMAGE_ID[0..3] | RO | 128-bit image identifier, least-significant word first |
| 0x018–0x024 | BUILD_ID[0..3] | RO | 128-bit build identifier, least-significant word first |
| 0x028 | CAPABILITIES_LO | RO | Protocol capability flags; bit allocation TBD |
| 0x02C | CAPABILITIES_HI | RO | Protocol capability flags; bit allocation TBD |
| 0x030 | SITE_PRESENT_BITMAP | RO | Bit n-1 = implemented Site n; **not** reserved-window presence |
| 0x034 | SITE_READY_BITMAP | RO | Bit n-1 = locally ready Site n; must be subset of PRESENT |
| 0x038 | PPU_STATUS | RO | Diagnostic status; encoding TBD |
| 0x03C | HW_REVISION | RO | Hardware revision; encoding TBD |
| 0x040 | SCRATCH | RW | 32-bit full-word storage; no electrical/protocol side effects |
| 0x044–0xFFF | RESERVED | — | Reject access; no speculative read/write |

For the initial common-only FPGA prototype, SITE_PRESENT_BITMAP and SITE_READY_BITMAP **must be zero**. For a later four-Site image, PRESENT may become 0xF only after all four engines are instantiated and verified. READY is independently derived from each Site state; it is not inferred from PRESENT or from a passing register self-test. A four-Site address reservation does not imply four working channels.

## Register self-test

After validating actual image load provenance and the global MAGIC/ABI, save SCRATCH, write/read/compare `0x00000000`, `0xFFFFFFFF`, `0xAAAAAAAA`, `0x55555555`, `0x12345678`, then restore original value in a `finally` path. Serialize the test against other users of SCRATCH; do not access any SWD Site registers or DUT pins. A failed restore is a failure, not a PASS. This proves only basic PS↔PL register access, not protocol functionality, timing, board IO or programming.

## Driver and integration constraints

- One common register implementation and one common access API per loaded image, not four copies.
- Reuse the existing authorized PS MMIO ownership/lease and ARMv7 32-bit access safeguards; do not add an alternate `/dev/mem` path.
- SWD Site windows each require their own independent command, response, FIFO, IRQ, cancellation, error and safe-off semantics when implemented in a later PR.
- The new C and Python APIs must use this new ABI consistently; no old ABI v5 offsets or compatibility fallback.
- An unimplemented window must return an AXI error once a full AXI decoder exists. The present RTL common-register candidate is **not** an AXI-Lite slave and does not establish that behavior.
- Physical base, reset/clock, AXI4-Lite handshakes, WSTRB, interconnect mapping, build metadata, simulation and ARMv7 hardware verification remain integration work. No deploy/merge/hardware access is authorized by this document.
