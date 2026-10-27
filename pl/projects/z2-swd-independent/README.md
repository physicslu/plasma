# PYNQ-Z2 two independent AXI SWD Sites — Gate 1 source-only

**Approved architecture:** [ADR-0005](../../../docs/adr/0005-independent-swd-ip-guarded-bitbang.md). **Build standard:** [ADR-0004](../../../docs/adr/0004-project-isolated-fpga-build-path2-operator-cli.md).

**State (2026-10-27):** `INDEPENDENT_SITE_AXI_RTL_HOST_SIM_PASS`, `SWPC_VIVADO_HOST_BUILD_PASS`, `BIT_HWH_HASHES_VERIFIED`; **EXTERNAL_IO_TIMING_BLOCKED (2 input + 4 output TIMING-18), Z2_HIL_NOT_RUN, OPENOCD_DEBUG_BRIDGE_NOT_IMPLEMENTED**. The Project has real host-only BIT/HWH results, but is **not a qualified deployable Image or programming-ready controller**. See [external-timing-audit.md](external-timing-audit.md).

Architecture:
- PS7 100-MHz FCLK0, M_AXI_GP0, synchronised reset.
- A conventional **1-input/2-output AXI Interconnect**. It routes MMIO requests only, not SWD bit clocks or job scheduling.
- SWD Site 1 module `plasma_swd_site_axi_lite` at proposed `0x43C01000`; physical JA SWCLK Y18, SWDIO Y19.
- SWD Site 2 same **independent AXI slave IP** at proposed `0x43C02000`; physical JB SWCLK W14, SWDIO Y14.
- Each Site has its own transaction FSM, SWCLK divider, per-Site pending command/response, fault, and **exclusive** Normal and guarded Bitbang Debug modes; disabled mode drives SWCLK low and SWDIO Hi-Z.
- **Gate 1 owner-approved HW maximum DESIGN TARGET = 12.5 MHz, not a fixed working speed.** In both AXI and standalone transaction FSM, `MIN_HALF_PERIOD=4` at FCLK0=100 MHz. Each Site independently accepts programmable divider `N >= 4`; normal-mode SWCLK=`100 MHz / (2*N)`. Power-up register `N=500` still means **100 kHz default**. Invalid `N=2` (25 MHz) and `N=3` (16.67 MHz) are rejected, without modifying the stored setting. Higher-layer PS/OpenOCD/IC Programming Profiles determine requested/qualified working speeds independently; this **does not qualify any DUT or off-board clock rate**.
- Current prototype is **one command in flight + one retained completion, not the planned 16-deep FIFOs**. IRQ is not wired to PS7; per-Site output remains diagnostic. No SWJ_SEQUENCE, OpenOCD adapter or qualified PS MMIO implementation yet.

New files:
- `pl/rtl/swd/plasma_swd_transaction_engine.sv` and `plasma_swd_site_axi_lite.sv`
- `pl/projects/z2-swd-independent/create_project.tcl`, `create_block_design.tcl`, `build_bitstream.tcl`
- `pl/constraints/pynq-z2/z2-swd-independent.xdc`
- `pl/sim/swd_two_site_axi_tb.sv` and Cocotb tests

Per-Site registers (offset): `00 ID`, `04 STATUS`, `08 HALF`, `0C TIMEOUT`, `10 TX`, `14 CMD`, `18 META`, `1C RX`, `20 TAGGED_POP`, `24 LEVELS`, `28 CONTROL`, `2C FAULT`, `30 IRQ_EN`, `34 IRQ_LEVEL`, `38 MODE`, `3C DEBUG_DRIVE`, `40 DEBUG_SAMPLE`. Current Site ID is `0x00020001/2`, not the historical MPE global image ABI.

Bitbang `DEBUG_DRIVE` bits: CLK=0, DATA_OUT=1, OE=2; the hardware accepts changes to DATA_OUT/OE only when the clock was low **and remains low**. Issue distinct writes for data/direction setup and subsequent clock transition. Switching mode demands normal disabled, no active command/completion and Debug pad CLK=0/OE=0; Normal/Debug can never both drive SWDIO. **This is a guard, not a substitute for PS-side process lease, OS authority or I/O-voltage safety.**

**OpenOCD SWD Debug blocker:** `v0.12.0` `remote_bitbang` is `jtag_only`. OpenOCD release/version and remote SWD Bridge protocol must be locked and independently qualified; do not assume current 0.12.0 can use these registers via remote_bitbang. Do not silently upgrade qualified OpenOCD MCU providers or fall back to obsolete WordPort/GPIO.

Vivado 2026.1 actually completed synthesis, implementation and BIT/HWH on SWPC using the reviewed SHA-pinned Path 2 `operator-cli` entrypoint. Baseline real Host Build [run #40482166100](https://github.com/physicslu/plasma/actions/runs/40482166100); subsequent [run #40485462844](https://github.com/physicslu/plasma/actions/runs/40485462844) proved six TIMING-18 external I/O omissions remain. The next Build captures routed FPGA datasheet and I/O pad reports. **Internal WNS/DRC success is not off-board target timing qualification**. New 12.5 MHz target must be checked against **the re-routed exact-source FPGA-only budget**; six missing off-board I/O delay constraints remain open until actual target/cable min-max budget is supported by evidence. Neither RTL simulation nor Host Build grants permission to load Z2 FPGA or access DUT.

Next: obtain per-DUT SWD target and Pmod/cable timing envelopes; derive min/max off-board timing budgets and justified XDC or constrained serial-interface method, complete full Image Manifest/archive, rerun real SWPC report checks, then separately authorize real hardware bring-up. Preserve the installed Image, Root Guard and Golden Restore.
