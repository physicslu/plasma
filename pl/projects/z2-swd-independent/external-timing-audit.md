# Independent dual-Site SWD external timing: real TIMING-18 audit

Status: EXTERNAL_IO_TIMING_NOT_QUALIFIED. This is not a zero-warning signoff and grants no hardware/deployment permission.

## Evidence

SWPC Path 2 operator-cli real Vivado 2026.1 run #40482166100, PR #1189 source ccec0e29c5852e24c33f4a491a9a56504f9b4a6c, archived artifact #12722609170:
- reports/methodology.rpt: six TIMING-18 Missing input or output delay Warnings, referenced to clk_fpga_0. They are missing *constraints*, not six observed negative slack violations.
- reports/check_timing.rpt: no_input_delay (2) swdio_site1 and swdio_site2; no_output_delay (4) swclk_site1, swclk_site2, swdio_site1, swdio_site2. no_clock=0, unconstrained_internal_endpoints=0.
- routed internal setup WNS +1.707ns / TNS 0; hold WHS +0.041ns / THS 0. These metrics do not establish external SWD timing.
- constraints/pynq-z2/z2-swd-independent.xdc contains only four LOC/IOSTANDARD LVCMOS33 assignments. No off-chip timing or exceptions.

## First-principles constraint problem

- FPGA PS7 FCLK0 = 100 MHz; RTL generates SWCLK from a *runtime-programmable* per-Site half-period counter. Current minimum half-period = 2 fabric cycles = 20ns, so maximum programmable SWCLK nominally 25MHz. This is NOT a proven safe frequency for a target or cable.
- When debugger drives SWDIO, RTL updates its value near SWCLK falling; target samples SWDIO at subsequent SWCLK rising. The available half-period must cover FPGA output clock-to-data skew, board/cable skew, target setup/hold, load and variation.
- When target drives SWDIO, target can change SWDIO on SWCLK rising; FPGA samples near SWCLK falling. The half-period must cover SWCLK route out, target tCO, target-to-FPGA data return, FPGA input setup and PVT variation. SWDIO turnaround/OE needs separate contention tests.
- OpenOCD Debug Bitbang is controlled by MMIO transitions and does not have a single fixed period. One nominal 100MHz virtual SWD clock would NOT match real hardware.
- Per-Site clock-to-data skew and target timing must be analyzed at the *fastest admitted operating divider* and min/max PVT corners; do not substitute a convenient 0ns delay, blanket false paths, fictional synchronous interface or artificial timing exceptions.

Arm source: https://documentation-service.arm.com/static/622222b2e6f58973271ebc21 (SWD §B4.3: target samples SWDIO at rising edge, target-driven SWDIO changes start at rising edge).
AMD Vivado 2026.1 source: https://docs.amd.com/r/en-US/ug906-vivado-design-analysis/TIMING-18-Missing-Input-or-Output-Delay
AMD Vivado 2026.1 XDC min/max guides:
https://docs.amd.com/r/en-US/ug903-vivado-using-constraints/Use-of-set_input_delay-Command-Options
https://docs.amd.com/r/en-US/ug903-vivado-using-constraints/Use-of-set_output_delay-Command-Options

## Gate to replace the six warnings with real coverage

1. Lock target-device supported SWD timing: tCO(min/max), tSU/tH, frequency, VDD/VIO across target PVT. Do not imply Blue Pill-only figures qualify all PLASMA ICs.
2. Establish maximum Pmod-to-DUT connector/cable propagation and skew; obtain board-specific trace data, load and grounding. JA may share Raspberry Pi header traces.
3. Obtain routed FPGA clock/data output skew, SWDIO input capture path and IOBUF OE timing under both Sites; run output- and input-direction checks.
4. Author source-controlled justified clock-relationship and set_input_delay/set_output_delay min AND max budget (or a narrowly scoped, independently reviewed protocol exception if STA truly cannot express variable-rate behavior). Every numerical value needs a source or explicit engineering-envelope derivation; no invention or masking.
5. Rebuild via SHA-pinned Path 2; validate updated check_timing, methodology, routed external-interface timing, budget and simulator/real-HIL proof. Real Pmod/DUT timing remains HIL NOT_RUN until separately approved.

Interim disposition: SWPC SYNTH/IMPL/DRC/PAD MAP PASS, but external IO timing = BLOCKED_INPUT_DELAY_2_OUTPUT_DELAY_4. Artifact verifiers must state this explicitly even when the Vivado host-build process exits 0. Do not deploy this provisional bitstream.
