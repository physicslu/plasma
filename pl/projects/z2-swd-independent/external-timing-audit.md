# Independent dual-Site SWD external timing: real TIMING-18 audit

Status: EXTERNAL_IO_TIMING_NOT_QUALIFIED. This is not a zero-warning signoff and grants no hardware/deployment permission.

## Evidence

SWPC Path 2 operator-cli real Vivado 2026.1 run #40482166100, PR #1189 source ccec0e29c5852e24c33f4a491a9a56504f9b4a6c, archived artifact #12722609170:
- reports/methodology.rpt: six TIMING-18 Missing input or output delay Warnings, referenced to clk_fpga_0. They are missing *constraints*, not six observed negative slack violations.
- reports/check_timing.rpt: no_input_delay (2) swdio_site1 and swdio_site2; no_output_delay (4) swclk_site1, swclk_site2, swdio_site1, swdio_site2. no_clock=0, unconstrained_internal_endpoints=0.
- routed internal setup WNS +1.707ns / TNS 0; hold WHS +0.041ns / THS 0. These metrics do not establish external SWD timing.
- constraints/pynq-z2/z2-swd-independent.xdc contains only four LOC/IOSTANDARD LVCMOS33 assignments. No off-chip timing or exceptions.

## First-principles constraint problem

- FPGA PS7 FCLK0 = 100 MHz; RTL generates SWCLK from a *runtime-programmable* per-Site half-period counter. The **historical first build** admitted minimum half-period 2 (25MHz); current candidate enforces minimum 4 (12.5MHz). Neither constitutes a target/cable-qualified frequency.
- When debugger drives SWDIO, RTL updates its value near SWCLK falling; target samples SWDIO at subsequent SWCLK rising. The available half-period must cover FPGA output clock-to-data skew, board/cable skew, target setup/hold, load and variation.
- When target drives SWDIO, target can change SWDIO on SWCLK rising; FPGA samples near SWCLK falling. The half-period must cover SWCLK route out, target tCO, target-to-FPGA data return, FPGA input setup and PVT variation. SWDIO turnaround/OE needs separate contention tests.
- OpenOCD Debug Bitbang is controlled by MMIO transitions and does not have a single fixed period. One nominal 100MHz virtual SWD clock would NOT match real hardware.
- Per-Site clock-to-data skew and target timing must be analyzed at the *fastest admitted operating divider* and min/max PVT corners; do not substitute a convenient 0ns delay, blanket false paths, fictional synchronous interface or artificial timing exceptions.

Arm source: https://documentation-service.arm.com/static/622222b2e6f58973271ebc21 (SWD §B4.3: target samples SWDIO at rising edge, target-driven SWDIO changes start at rising edge).
AMD Vivado 2026.1 source: https://docs.amd.com/r/en-US/ug906-vivado-design-analysis/TIMING-18-Missing-Input-or-Output-Delay
AMD Vivado 2026.1 XDC min/max guides:
https://docs.amd.com/r/en-US/ug903-vivado-using-constraints/Use-of-set_input_delay-Command-Options
https://docs.amd.com/r/en-US/ug903-vivado-using-constraints/Use-of-set_output_delay-Command-Options

## Routed FPGA-only half-cycle budget (new measured evidence)

Real Vivado 2026.1 [run #40487489843](https://github.com/physicslu/plasma/actions/runs/40487489843), [archive #12726195560](https://github.com/physicslu/plasma/actions/runs/40487489843/artifacts/12726195560) generated **report_datasheet -show_all_corners -show_oe_timing** and **report_io**.

At the SLOW process corner, `clk_fpga_0` launch-to-SWCLK-pad maximum is Site 1 **13.070 ns**, Site 2 **14.118 ns**. SWDIO Input Setup to the same 100 MHz FCLK capture register is Site 1 **5.329 ns**, Site 2 **6.276 ns**. Summed FPGA-only RX minimum half-cycle bounds (assuming **zero target tCO, zero cable delay, zero skew/uncertainty**, which are nonphysical optimistic assumptions) are **18.399 ns** and **20.394 ns**, respectively.

At the historical `half_period=2` (20 ns / 25 MHz), illustrative FPGA-only margin: Site 1 **+1.601 ns**, Site 2 **−0.394 ns**. Thus the historical 25 MHz register setting could **not** be qualified even before any real target or wire delay. These derived numbers are a **path feasibility audit**, not a formal STA max/min SWD interface sign-off; target/board and IOBUF turnaround are still missing.

**Owner-approved Gate 1 revision:** both per-Site AXI register and engine now reject `half_period <4`, while the independent Site register reset `half_period=500` (100 kHz) remains unchanged. `N=4` is a **12.5 MHz design maximum candidate**, *not* the DUT-qualified operating frequency. Upper-layer PS/OpenOCD/IC Programming Profile requests each Site's divider dynamically while idle; `N=2`/`N=3` remain denied. Debug Bitbang remains an independent host-driven mode without a fixed-rate SWCLK. `12.5 MHz` must undergo new routed Vivado internal timing, FPGA-only 40 ns half-cycle feasibility check, and later external DUT/cable min/max timing plus separate authorized HIL before marked supported. Do not unconditionally release a 12.5 MHz host setting to devices.

The actual `report_io` confirms Site1 SWCLK Y18/SWDIO Y19 and Site2 SWCLK W14/SWDIO Y14, IO Bank 34, `LVCMOS33`, current implemented SLEW=`SLOW`, DRIVE=`12 mA`. These are **observed current implementation values**, not board-level signal-quality validation or deliberate final electrical selection.

## 12.5 MHz engineering sign-off distinction (Owner Gate 1)

At 100 MHz FCLK, the design candidate N=4 produces 12.5 MHz (40 ns half-cycle), N=500 produces the unchanged 100 kHz default, N=3 would exceed the candidate max (16.67 MHz) and must be rejected. Independent Site 1/2 dynamic dividers permit different speeds simultaneously.

**Actual 12.5MHz-capable pre-FIFO image evidence:** PR #1189 source `ff161d3bd8c9595999582266cf4817be1af565f2`, approved SWPC Path 2 `operator-cli` [run #40495512961](https://github.com/physicslu/plasma/actions/runs/40495512961), [archive #12729724467](https://github.com/physicslu/plasma/actions/runs/40495512961/artifacts/12729724467). Vivado 2026.1 routed setup WNS **+1.372ns**, TNS 0; hold WHS **+0.018ns**, THS 0; pulse WPWS **+4.020ns**, TPWS 0, DRC 0. These are *constrained internal paths only*. Actual 40ns SLOW corner FPGA-only RX budget is Site1 **13.446ns SWCLK pad tCO + 6.562ns input setup = 20.008ns**, ideal remaining **19.992ns**; Site2 **12.870 + 5.119 = 17.989ns**, ideal remaining **22.011ns**. It excludes target tCO, wire min/max delay, skew, uncertainty and electrical quality. `no_input_delay=2`, `no_output_delay=4`, TIMING-18×6 **still BLOCKED**. The actual BIT `f60534fbea13ed9982d029db6a15951cf6ea45c026cbb06db91167b7ef14b9e3` (SHA256) is **not** the later FIFO/IRQ/SWJ RTL. Any later changed HEAD needs a fresh routed report; never inherit these numbers as the revised IP's timing signoff.

This gate intentionally does **not** change external timing qualification merely because the candidate 12.5 MHz divider is accepted or internal WNS is positive. Maintain `no_input_delay=2`, `no_output_delay=4` and `TIMING-18=6` as BLOCKED until defensible target/board reference-clock timing model, both -min/-max constraints (or separately reviewed justified STA model), and permitted HIL prove the actual SWD interface.

## Gate to replace the six warnings with real coverage

1. Lock target-device supported SWD timing: tCO(min/max), tSU/tH, frequency, VDD/VIO across target PVT. Do not imply Blue Pill-only figures qualify all PLASMA ICs.
2. Establish maximum Pmod-to-DUT connector/cable propagation and skew; obtain board-specific trace data, load and grounding. JA may share Raspberry Pi header traces.
3. Obtain routed FPGA clock/data output skew, SWDIO input capture path and IOBUF OE timing under both Sites; run output- and input-direction checks.
4. Author source-controlled justified clock-relationship and set_input_delay/set_output_delay min AND max budget (or a narrowly scoped, independently reviewed protocol exception if STA truly cannot express variable-rate behavior). Every numerical value needs a source or explicit engineering-envelope derivation; no invention or masking.
5. Rebuild via SHA-pinned Path 2; validate updated check_timing, methodology, routed external-interface timing, budget and simulator/real-HIL proof. Real Pmod/DUT timing remains HIL NOT_RUN until separately approved.

Interim disposition: SWPC SYNTH/IMPL/DRC/PAD MAP PASS, but external IO timing = BLOCKED_INPUT_DELAY_2_OUTPUT_DELAY_4. Artifact verifiers must state this explicitly even when the Vivado host-build process exits 0. Do not deploy this provisional bitstream.
