# SWD NORMAL / PS ARMv7 MMIO Gate 1 Host-only boundary

**PR #1189 Draft.** This is a source-only integration contract, **not** an
actual OpenOCD C adapter, Linux driver, deployed Image or DUT qualification.

## NORMAL transaction compatibility contract

`software/python/plasma_interfaces/swd_native_normal_contract.py` models
the proposed OpenOCD SWD adapter callbacks `read_reg`, `write_reg`,
`switch_seq` and `run`, using the existing `SwdSiteController` as
the **single source of register sequencing and command encoding**.

- Caller must already own and verify exact Image/Manifest, exclusive Site
  lease, ABI v5 identity, qualified voltage and NORMAL mode. The module
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

## ABI v5 native LinuxMMIO / Site Lease integration (Host-only)

The project now supplies `swd_native_linux_mmio.py` with
`swd_site_aperture(site_id)` and `SwdNativeLinuxMMIOPort`. These reuse
the existing `LinuxMMIO` and `SiteMMIO` ownership/mapping APIs, plus
the existing SHA-pinned `ARMv7DMBBarrier`, rather than opening an alternate
driver/backend or resurrecting the old bitbang WordPort.

- The independently leased Site 1/2 bases are **candidates**
  `0x43C01000` and `0x43C02000`; they still require exact-HWH verification.
- Readable registers: `00 04 08 0C 18 1C 24 28 2C 30 34 38`.
  Writable registers: `08 0C 10 14 20 28 2C 30 34 38 44 48 4C
  50 54 58 5C 60 64` (hexadecimal byte offsets). Any other offset,
  including retired SWD Debug offsets `0x3C/0x40`, is denied locally
  without MMIO. The hardware additionally returns SLVERR for them.
- The adapter requires an **already-open** `LinuxMMIO`, an exclusive
  correctly numbered `SiteMMIO` lease and its exact per-Site access policy.
  No FPGA download, Root authorization, voltage authorization or OS
  privilege is acquired by construction.
- ARMv7 hardware access requires `ARMv7DMBBarrier`; an injected fake
  barrier is allowed ONLY on a non-symlink REGULAR FILE under Host-only CI.
  Barrier uncertainty poisons the **entire shared LinuxMMIO mapping**, not
  merely one Site. The associated Source/Test cases cover 2-Site ownership,
  v5 identities, wrong Site/ABI, retired offsets, invalid width, symlink,
  stale lease and cross-Site fail closed.
- `LinuxMMIO` currently implements native CPython
  `memoryview(...).cast("I")` word reads/writes. These tests **do not
  prove ARMv7 LDR/STR instructions, Device memory page attributes,
  posted AXI completion or physical bus abort recovery**. ARMv7 ELF/
  disassembly and real PS7/PL/MMIO qualification remain NOT_RUN.

## Exact OpenOCD 5088db4c source API mismatch (C Adapter still pending)

PR #1196 used OpenOCD `0.12.0+dev` source
`5088db4c9154ca833c6d558381074b33672e127a`, **not** the
`v0.12.0` release. Its
`src/jtag/swd.h` `struct swd_driver` has
`init(void)`, `switch_seq(enum swd_special_seq)`,
`read_reg(uint8_t cmd, uint32_t *value, uint32_t ap_delay_hint)`,
`write_reg(uint8_t cmd, uint32_t value, uint32_t ap_delay_hint)` and
`run(void)`. OpenOCD's command-byte bit layout is **not** the private
9-bit FPGA `encode_transfer` layout. A real C adapter must decode
SWD APnDP, RnW, address and parity, preserve queued result-pointer lifetime,
correctly handle AP delay hints, DPv2 TARGETSEL/no-ACK special behavior,
WAIT/FAULT/uncertain write semantics, and real SWJ sequence enumeration.
A Python method name match is **not** source-level API compatibility.

A pinned source-level Host-only bridge now exists as
`swd_opencd_5088_command_contract.py`. It validates OpenOCD `swd_cmd()`
parity, APnDP, RnW and DP/AP register offsets, translates command bytes into
the **different** PLASMA private 9-bit command through the shared
`SwdNativeNormalContract`, and supports explicit 1..256-bit LSB-first SWJ
payloads. Cross-layer tests assert that OpenOCD DP IDCODE read `0x24`
becomes FPGA private `0x02`, while OpenOCD AP write `0x3A` becomes
private `0x0D`. They also test 64/136/224-bit atomic sequences and negative
callback direction/parity/length cases.

**Important fail-closed scope gaps:** OpenOCD's `ap_delay_hint > 0` is
rejected rather than guessed as the FPGA's hardcoded 8 idle cycles; DPv2
no-ACK TARGETSEL is rejected rather than falsely claiming an ACK. The real
`enum swd_special_seq` mapping, OpenOCD queue result-pointer lifetime,
AP posted-read ordering/RDBUFF, error-code conversion, C driver integration
and native cross-compilation are still **NOT_IMPLEMENTED**.

Neither this document nor the two Host-only integration contracts
implements or compiles a native OpenOCD C adapter.

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

Still blocking: target-specific native 32-bit access width qualification,
ARMv7 disassembly (LDR/STR, DMB) and Device mapping attributes; PS7 AXI
error/interrupt admission; fresh exact-HEAD Vivado Timing/DRC/BIT/HWH;
actual Z2 HIL; version-qualified OpenOCD Native C adapter.

**Status:** HOST_ONLY_CONTRACT_CANDIDATE, ARMV7_NATIVE_WIDTH_NOT_RUN,
OPENOCD_NATIVE_C_ADAPTER_NOT_RUN, EXTERNAL_IO_TIMING_BLOCKED,
DRAFT_NO_MERGE_NO_DEPLOY.
