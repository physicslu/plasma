# PYNQ-Z2 two independent AXI SWD Sites — Gate 1 source-only

**Approved architecture:** [ADR-0005](../../../docs/adr/0005-independent-swd-ip-guarded-bitbang.md). **Build standard:** [ADR-0004](../../../docs/adr/0004-project-isolated-fpga-build-path2-operator-cli.md).

**State:** `INDEPENDENT_SITE_AXI_RTL_HOST_SIM_PASS` for separately instantiated SWD IPs; **VIVADO_BUILD_NOT_RUN / HWH_NOT_VERIFIED / Z2_HIL_NOT_RUN / OPENOCD_DEBUG_BRIDGE_NOT_IMPLEMENTED**. This new Project is a *source candidate*, not an FPGA Image or programming-ready controller.

Architecture:
- PS7 100-MHz FCLK0, M_AXI_GP0, synchronised reset.
- A conventional **1-input/2-output AXI Interconnect**. It routes MMIO requests only, not SWD bit clocks or job scheduling.
- SWD Site 1 module `plasma_swd_site_axi_lite` at proposed `0x43C01000`; physical JA SWCLK Y18, SWDIO Y19.
- SWD Site 2 same **independent AXI slave IP** at proposed `0x43C02000`; physical JB SWCLK W14, SWDIO Y14.
- Each Site has its own transaction FSM, SWCLK divider, per-Site pending command/response, fault, and **exclusive** Normal and guarded Bitbang Debug modes; disabled mode drives SWCLK low and SWDIO Hi-Z.
- Current prototype is **one command in flight + one retained completion, not the planned 16-deep FIFOs**. IRQ is not wired to PS7; per-Site output remains diagnostic. No SWJ_SEQUENCE, OpenOCD adapter or qualified PS MMIO implementation yet.

New files:
- `pl/rtl/swd/plasma_swd_transaction_engine.sv` and `plasma_swd_site_axi_lite.sv`
- `pl/projects/z2-swd-independent/create_project.tcl`, `create_block_design.tcl`, `build_bitstream.tcl`
- `pl/constraints/pynq-z2/z2-swd-independent.xdc`
- `pl/sim/swd_two_site_axi_tb.sv` and Cocotb tests

Per-Site registers (offset): `00 ID`, `04 STATUS`, `08 HALF`, `0C TIMEOUT`, `10 TX`, `14 CMD`, `18 META`, `1C RX`, `20 TAGGED_POP`, `24 LEVELS`, `28 CONTROL`, `2C FAULT`, `30 IRQ_EN`, `34 IRQ_LEVEL`, `38 MODE`, `3C DEBUG_DRIVE`, `40 DEBUG_SAMPLE`. Current Site ID is `0x00020001/2`, not the historical MPE global image ABI.

Bitbang `DEBUG_DRIVE` bits: CLK=0, DATA_OUT=1, OE=2; the hardware accepts changes to DATA_OUT/OE only when the clock was low **and remains low**. Issue distinct writes for data/direction setup and subsequent clock transition. Switching mode demands normal disabled, no active command/completion and Debug pad CLK=0/OE=0; Normal/Debug can never both drive SWDIO. **This is a guard, not a substitute for PS-side process lease, OS authority or I/O-voltage safety.**

**OpenOCD SWD Debug blocker:** `v0.12.0` `remote_bitbang` is `jtag_only`. OpenOCD release/version and remote SWD Bridge protocol must be locked and independently qualified; do not assume current 0.12.0 can use these registers via remote_bitbang. Do not silently upgrade qualified OpenOCD MCU providers or fall back to obsolete WordPort/GPIO.

The local Tcl project has **not been elaborated by Vivado**, so AXI module parameter inference, PS7 interconnect/reset wiring, generated HWH and pad placement must be tested before the next approval gate. `build_bitstream.tcl` is an inert version-controlled build input, not evidence that it ran; it must eventually be invoked under a reviewed SHA-pinned Path 2 `operator-cli` wrapper. Host RTL CI does not grant permissions to load the FPGA or access DUT.

Before host-build qualification: complete and test an **independent HWH/BIT/Manifest verifier**, the SHA-pinned Path 2 Python entrypoint and on-host Vivado execution. Preserve existing installed Image, Root Guard and Golden Restore.
