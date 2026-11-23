# OPP FPGA Register Map v1 — new ABI, four Site windows (Gate 1)

Status: **candidate, source-only**. The Common Registers ABI v1 is a new, independent ABI, not a deployed image or a claim of four implemented SWD engines. **Existing, validated SWD-v5 registers, physical Site bases and OpenOCD path are preserved unchanged**; the candidate Common map must not be interpreted as a replacement for SWD-v5. No legacy SWD-v5 offsets are reused inside the new Common register block.

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

Candidate four-Site-only window formula: `site_offset(n) = 0x1000 * n`, n=1..4. This is **not** the product-wide 8-Site allocation contract and does not constrain later IP families. Each Site window is **reserved, not populated** until its SWD register contract and engine exist. No aliasing of unimplemented Sites to Site 1, no implicit multiplexing or shared Site FSM. Software must not probe reserved windows to detect hardware.

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

## Owner decision (2026-11-22): product-wide reserved address-space policy

This section records an **approved planning convention**, not a new physical AXI decode, a change to the SWD-v5 ABI, or a claim that a 16 MiB aperture is currently available on PYNQ-Z2.

- Plan a **16 MiB logical PLASMA FPGA MMIO address budget** for the product family, subject to checking the actual PS7 Address Editor, XSA/HWH, Linux device tree and existing mappings before choosing any physical base or implementing decode. The 16 MiB figure is a planning target, not an already assigned contiguous physical aperture.
- Use **64 KiB as the preferred planning allocation granularity for peripheral IP families**, with larger reserved regions when justified (e.g. multi-Site SWD, I2C, SPI, UART/ISP, power control and pin matrix). A reserved window consumes address space, not necessarily BRAM or instantiated hardware.
- Keep a **single globally governed, non-overlapping logical address allocation** for Common and each peripheral family, even across mutually exclusive bitstreams, to maintain stable software bindings. Each loaded image must also have unambiguous AXI decoding. Reuse across images is technically possible but is **not** the PLASMA product convention.
- Separate **global allocation**, **peripheral register offsets**, and **per-Site windows**. Common identity/capability ABI is independent of SWD/I2C/SPI engine ABIs; an absent IP must be declared absent and must not be probed through an unmapped address.
- **Preserve the validated SWD-v5 PS-local OpenOCD path and its physical Site 1/2 bases** (`0x43C01000`, `0x43C02000`) unchanged. Do not reinterpret this document's candidate relative offsets as an authorization to remap those sites or to rebuild OpenOCD.
- The earlier 64 KiB candidate map in this document remains a **source-only, unintegrated proposal**. Its `0x0000–0x0FFF` Common and `0x1000–0x4FFF` Site offsets are **not** a frozen product-wide allocation and must be reconciled against the above policy and actual hardware map before RTL/bitstream integration. No physical address or 16 MiB decoder is assigned by this decision.

**PR #1528 Gate 2 implication:** review this policy as a compatibility constraint; do not expand the PR into I2C/SPI IP implementation, 8-Site hardware, SWD-v5 remapping, deployment, or Z2/DUT operation. Any future allocation table must explicitly identify actual physical bases, window sizes, owners and ABI versions before implementation.

## Gate 2 delta review (2026-11-23; source inspection only)

- **Observed:** `opp_common_axi_lite_v1.sv` implements a 12-bit AXI4-Lite register slave with independent AW/W buffering, WSTRB writes to SCRATCH, and SLVERR for unimplemented offsets. The Python `OPPCommonRegisters` and C `plasma_opp_common` APIs implement identity checks and SCRATCH save/test/restore.
- **Observed CI:** commit `54d5e75d3aad98cbfb254443c5c549a0521479ae` has ten completed successful GitHub Actions workflows. This establishes workflow status, **not** that each workflow executed the new Common RTL simulation or that the RTL is physically integrated.
- **Not verified:** Common RTL-specific AXI simulation coverage and executed results; board-specific PS7 Address Editor / XSA / HWH / Device Tree physical mapping; a single synthesized bitstream containing both Common and the unchanged SWD-v5 IP; target ARMv7 MMIO access-width and real Z2 HIL.
- **Scope guard:** do not treat candidate four-Site window reservations as implemented engines, do not infer 8-Site support from the product-wide policy, and do not merge/deploy/load FPGA or access DUT under this documentation review.
- **Gate 2 readiness:** **NOT READY** for physical-integration claims. A source-only Gate 2 may be considered only after the Common-specific regression is identified and its actual execution evidence reviewed, with all unperformed physical stages explicitly NOT_RUN.

## Z2 two-Site physical integration candidate (Gate 1 Host-only)

The retained exact `d0add58c` HWH maps PS7 `M_AXI_GP0` Site 1 to
`0x43C01000–0x43C01FFF` and Site 2 to `0x43C02000–0x43C02FFF`, with no
other `MEMRANGE`. The paired historical Manifest records the enclosing Linux
resource `0x43C00000–0x43C0FFFF`, named `43c00000.audio-codec-ctrl`; this
resource is **not** proof of a Common slave at its base. The integration
allocates Common to `0x43C03000–0x43C03FFF`, disjoint from both existing AXI
slaves and within that recorded resource. The new HWH verifier requires
exactly these three regions; actual new HWH and Linux ownership remain
unverified until a source-pinned Host Build and separately authorized HIL.

This image instantiates only Site 1 and Site 2. Its Common registers report
`SITE_PRESENT=0x3`, `SITE_READY=0`, `CAPABILITIES=0`, and `PPU_STATUS=0`.
Ready is conservatively false until live admission is proven; reserved Site
3/4 logical windows in the earlier proposal are not physical AXI slaves.
`IMAGE_ID` names the image family, and `BUILD_ID` is the first 128 bits of
the exact Host Build source SHA. The paired candidate Manifest is emitted
only after BIT/HWH/BIN verification; the installed `d0add58c` Manifest and
protected Root/Golden Recovery remain unchanged.
