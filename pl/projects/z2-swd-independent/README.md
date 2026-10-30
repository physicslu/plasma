# PYNQ-Z2 two independent AXI SWD Sites — Gate 1 Host Build candidate

**Approved architecture:** [ADR-0006](../../../docs/adr/0006-independent-swd-engine-and-future-gpio-bus.md) (supersedes ADR-0005). **Build standard:** [ADR-0004](../../../docs/adr/0004-project-isolated-fpga-build-path2-operator-cli.md).

## Common Path 2 Vivado Host Build (PR #1189 Gate 1 continuation)

The project owns `host-build.json` for the merged generic `vivado-host-build`
capability. An Owner/SHA-pinned Issue #981 Work Order selects
`pl/projects/z2-swd-independent` and Vivado `2026.1` with an exact PYNQ-Z2
Board Files SHA. The trusted existing Dispatcher/Runner verifies the source,
project contract and board provenance; no separate SWD build Dispatcher,
Stage, Runner or Workflow is required. The existing historical
`operator-cli` SWD build evidence remains valid **only for its recorded SHA**.

`build_bitstream.tcl` emits the exact generic success marker only after actual
synthesis, implementation, constrained-path slack/DRC and artifact production.
`verify_hwh.py` implements the generic `verify_artifacts(..., build=...)`
interface while retaining the original standalone CLI. Both paths require
exact Site1/Site2 AXI regions, four Pmod pads, XDC, BIT/HWH and seven routed
reports, including `check_timing`, `datasheet_io` and `io_pad_configuration`.
The receipt includes those hashes and the explicitly **unqualified** off-board
SWD timing result. `TIMING-18` (historically 2 missing input delays and 4
missing output delays) is never silently waived or transformed into HIL PASS.

The generic result is `HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED`; it is not
a deployable FPGA Image or permission to load a bitstream. Z2, FPGA Manager,
actual PS MMIO, OpenOCD, DUT and physical HIL remain `NOT_RUN` in this Gate.

**State (2026-10-27):** `INDEPENDENT_SITE_AXI_RTL_HOST_SIM_PASS` for the *prior* SHA-pinned Host Build; new FIFO/IRQ/SWJ RTL on PR #1189 requires exact-new-HEAD CI and Vivado revalidation. The previous `SWPC_VIVADO_HOST_BUILD_PASS` and `BIT_HWH_HASHES_VERIFIED` do **not** qualify the updated RTL. **EXTERNAL_IO_TIMING_BLOCKED (2 input + 4 output TIMING-18), Z2_HIL_NOT_RUN, OPENOCD_NATIVE_ADAPTER_NOT_IMPLEMENTED**. This is **not a qualified deployable Image or programming-ready controller**. See [external-timing-audit.md](external-timing-audit.md).

Architecture:
- PS7 100-MHz FCLK0, M_AXI_GP0, synchronised reset.
- A conventional **1-input/2-output AXI Interconnect**. It routes MMIO requests only, not SWD bit clocks or job scheduling.
- SWD Site 1 module `plasma_swd_site_axi_lite` at proposed `0x43C01000`; physical JA SWCLK Y18, SWDIO Y19.
- SWD Site 2 same **independent AXI slave IP** at proposed `0x43C02000`; physical JB SWCLK W14, SWDIO Y14.
- Each Site has its own transaction FSM, SWCLK divider, **16-entry command FIFO and 16-entry retained response FIFO**, tagged head-only consumption, completion-event IRQ (RW1C), fault latch, and **OFF/NORMAL only**; disabled mode drives SWCLK low and SWDIO Hi-Z. No SWD-specific Debug pad path is present.
- **Gate 1 owner-approved HW maximum DESIGN TARGET = 12.5 MHz, not a fixed working speed.** In both AXI and standalone transaction FSM, `MIN_HALF_PERIOD=4` at FCLK0=100 MHz. Each Site independently accepts programmable divider `N >= 4`; normal-mode SWCLK=`100 MHz / (2*N)`. Power-up register `N=500` still means **100 kHz default**. Invalid `N=2` (25 MHz) and `N=3` (16.67 MHz) are rejected, without modifying the stored setting. Higher-layer PS/OpenOCD/IC Programming Profiles determine requested/qualified working speeds independently; this **does not qualify any DUT or off-board clock rate**.
- **FIFO contract (unqualified new RTL):** accepted CMD_PUSH snapshots tag/op/TX/HALF/TIMEOUT; hardware dispatches FIFO-order and never replays writes; full command queue returns AXI `SLVERR`, full response queue stops further command dispatch. HEAD `META`/`RX` remain stable until the exact 16-bit tagged `POP`, and a wrong tag returns `SLVERR`. `LEVELS` bits `[21:17]` are response count (0..16), `[11:7]` are command count (0..16), bit 1 response-not-empty, bit 0 command-not-empty. The autonomous engine can have one *additional* in-flight command; a full response queue prevents further dispatch, not an already in-flight transaction. An asynchronous completion sets sticky `IRQ_PENDING` bit 0, cleared only by writing 1 to offset `0x34`; POP does not acknowledge IRQ. `IRQ_ENABLE` controls the Site-local IRQ output, not the pending flag. IRQ has not been connected/qualified through PS7 GIC.
- **Fault cancellation:** parity, timeout and abort latch `ERROR`; pending commands stop dispatching. With the engine idle and fault latched, `NORMAL_CONTROL=4` explicitly drops unexecuted command FIFO entries without replay; results already retained remain available. The caller must reconcile dropped tags and **must not retry uncertain writes automatically**. Clear `ERROR` with RW1C only after queued commands/engine response are empty. All of this is HOST-ONLY until retested on real AXI/HWH/PS.
- **SWJ 1..256-bit atomic candidate:** `CMD_PUSH` bit 8 set; in legacy-length mode (staged `SWJ_LENGTH=0`) low byte 0 emits 64 ones + 8 idle (line reset), and 1..32 transmit that many `TX_DATA` bits LSB-first + 8 idle. For 33..256 bits, write all eight `SWJ_DATA0..7` 32-bit staging words at offsets `0x44..0x60`, then arm `SWJ_LENGTH` offset `0x64` with 33..256 and push command low byte equal to length modulo 256. The command FIFO snapshots the 256-bit staging buffer and exact 9-bit count; accepted SWJ push auto-disarms staging, preventing a later `0x100` reset from silently using the previous 256-bit length. No implicit splitting, no clock idle inserted inside a sequence. Host-only Icarus/Cocotb verifies 256-bit LSB-first and immutable staging, **not** physical timing.
- The `software/python/plasma_interfaces/swd_site.py` and Host-only NORMAL transaction/word32 boundary modules are the shared PS candidate; native ARMv7 MMIO/lease, real OpenOCD C adapter and physical HIL remain NOT_RUN. The SWD-only Debug Bitbang/Socket modules have been removed (no fallback). A generic GPIO Bus is a separate future Site peripheral, not an SWD mode.

New files:
- `pl/rtl/swd/plasma_swd_transaction_engine.sv` and `plasma_swd_site_axi_lite.sv`
- `pl/projects/z2-swd-independent/create_project.tcl`, `create_block_design.tcl`, `build_bitstream.tcl`
- `pl/constraints/pynq-z2/z2-swd-independent.xdc`
- `pl/sim/swd_two_site_axi_tb.sv` and Cocotb tests

Per-Site registers (offset): `00 ID`, `04 STATUS`, `08 HALF`, `0C TIMEOUT`, `10 TX`, `14 CMD`, `18 META`, `1C RX`, `20 TAGGED_POP`, `24 LEVELS`, `28 CONTROL`, `2C ERROR_RW1C`, `30 IRQ_EN`, `34 IRQ_PENDING_RW1C`, `38 MODE` (only OFF=0/NORMAL=1), `44..60 SWJ_DATA0..7` (write-only), `64 SWJ_LENGTH` (write-only). Retired `0x3C/0x40` Debug offsets and `MODE=2` always reject with AXI SLVERR; their pin-driving logic is physically absent. Candidate Site IDs **`0x00050001/2`** deliberately reject v4/v3/v2 identities. No installed Image was changed.

Vivado 2026.1 actually completed synthesis, implementation and BIT/HWH on SWPC using the reviewed SHA-pinned Path 2 `operator-cli` entrypoint. Baseline real Host Build [run #40482166100](https://github.com/physicslu/plasma/actions/runs/40482166100); subsequent [run #40485462844](https://github.com/physicslu/plasma/actions/runs/40485462844) proved six TIMING-18 external I/O omissions remain. The next Build captures routed FPGA datasheet and I/O pad reports. **Internal WNS/DRC success is not off-board target timing qualification**. New 12.5 MHz target must be checked against **the re-routed exact-source FPGA-only budget**; six missing off-board I/O delay constraints remain open until actual target/cable min-max budget is supported by evidence. Neither RTL simulation nor Host Build grants permission to load Z2 FPGA or access DUT.

Next: obtain per-DUT SWD target and Pmod/cable timing envelopes; derive min/max off-board timing budgets and justified XDC or constrained serial-interface method, complete full Image Manifest/archive, rerun real SWPC report checks, then separately authorize real hardware bring-up. Preserve the installed Image, Root Guard and Golden Restore.
