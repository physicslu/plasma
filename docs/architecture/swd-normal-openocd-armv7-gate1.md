# SWD NORMAL / PS ARMv7 MMIO Gate 1 Host-only boundary

**PR #1189 Draft.** This is a source-only integration contract, **not** an
actual OpenOCD C adapter, Linux driver, deployed Image or DUT qualification.

## NORMAL transaction compatibility contract

`software/python/plasma_interfaces/swd_native_normal_contract.py` models
the proposed OpenOCD SWD adapter callbacks `read_reg`, `write_reg`,
`switch_seq` and `run`, using the existing `SwdSiteController` as
the **single source of register sequencing and command encoding**.

- Caller must already own and verify exact Image/Manifest, exclusive Site
  lease, ABI v4 identity, qualified voltage and NORMAL mode. The module
  neither grants privileges nor opens any device.
- 16 entries is the bounded host queue, separate from the FPGA's 16-entry
  per-Site command/response FIFO. This prototype executes the queued
  operations **one at a time**; higher-throughput native pipelining is pending.
- Results preserve exact tag order, raw ACK and read data-valid. WAIT, FAULT,
  invalid ACK, timeout or uncertain MMIO **block** the adapter instance.
  No silent retries or write replays; no fabricated AP posted-read/RDBUFF.
- SWJ is one 1..256-bit LSB-first command (or 64-clock line reset). All
  physical SWCLK generation remains inside the independent PL FSM, not Linux.
- Site 1 and Site 2 are independent AXI windows. No MPE manager, no global
  SWD scheduler and no fallback to GPIO/WordPort or old remote_bitbang route.
- **Native C OpenOCD adapter = NOT_IMPLEMENTED.** Exact-version OpenOCD API,
  build, binary and target tests = NOT_RUN. Existing production OpenOCD
  0.12.0 remains untouched.

## ARMv7 MMIO word width contract

`software/python/plasma_interfaces/swd_mmio32_contract.py` checks
aligned, unsigned 32-bit accesses within one 4-KiB Site window, and
requires explicitly injected `read_word`, `write_word`, read-barrier and
write-barrier implementations. It deliberately does **not** open
`/dev/mem`, `/dev/uio`, mmap, Socket or an OS privilege boundary.

Mock tests demonstrate 32-bit **function calls and ordering only**. They
do not prove that CPython emits ARMv7 LDR/STR instead of byte stores.
`struct.pack_into("<I", ...)` cannot be substituted for architectural
MMIO width and ordering evidence.

Still blocking: target-specific 32-bit native accessor implementation,
ARMv7 disassembly (LDR/STR, DMB) and Device mapping attributes; PS7 AXI
error/interrupt admission; fresh exact-HEAD Vivado Timing/DRC/BIT/HWH;
actual Z2 HIL; version-qualified OpenOCD Native and Debug adapters.

**Status:** HOST_ONLY_CONTRACT_CANDIDATE, ARMV7_NATIVE_WIDTH_NOT_RUN,
OPENOCD_NATIVE_C_ADAPTER_NOT_RUN, EXTERNAL_IO_TIMING_BLOCKED,
DRAFT_NO_MERGE_NO_DEPLOY.
