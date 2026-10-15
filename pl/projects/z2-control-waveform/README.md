# PSPL-02 / SWD-00 — offline RTL candidate

**Status: software-only RTL candidate.** This is **not** a built or deployed Z2
bitstream. HIL-PSPL-01 Identity-only acceptance (2026-10-14) remains unchanged.

## Independent scope

- `pl/rtl/bus/pl_control_axi_lite.sv`: 32-bit AXI4-Lite, independent AW/W
  arrival, one outstanding read and one write response, B/R backpressure,
  active-low reset and WSTRB byte enables. Intended **new** 4 KiB aperture
  `0x40001000`; this RTL is **not connected to a Vivado Block Design yet**.
- `pl/rtl/site/swd_waveform_engine.sv`: 1..32 LSB-first bits, programmable
  2..65535 PS/PL-clock-cycle half-period, programmable drive/Hi-Z, input
  sampling at the end of the high phase, bounded completion, reset-safe Hi-Z.
  It is an independent clocked component; no AXI wrapper, integrated
  Command FIFO, pin assignment or externally connected IOBUF is claimed.

## PSPL-02 proposed register contract (not deployed)

| Offset | Access | Reset | Meaning |
|---|---|---|---|
| `0x00` | R/W | 0 | CONTROL; WSTRB applies per byte |
| `0x04` | R/O | `0xA5A55A5A` | STATUS = CONTROL XOR `0xA5A55A5A` |

Other offsets, unaligned accesses and STATUS writes return AXI SLVERR
inside this slave. Address-space decoding and the 4 KiB segment must
be implemented and separately verified in Vivado IP Integrator. The
existing Identity-only IP at `0x40000000` stays untouched.

## SWD-00 contract

`start` is a one-cycle command pulse. `bit_count` is 1..32 and
`half_period_cycles` is 2..65535; invalid commands generate a one-cycle
`done` plus sticky `error`. Successful commands emit `bit_count` SWCLK
pulses with idle-low clock. `swdio_oe` is asserted only if requested for
the transfer, deasserted on completion/reset; receiving is Hi-Z for the
entire command. Data is LSB-first. A new START during BUSY is not queued
and sets sticky ERROR; reset aborts and tri-states.

This primitive is **not an SWD Transaction Master**: ACK/parity handling,
explicit SWD turnaround, WAIT/FAULT recovery, DP/AP transactions,
target-reset pin, power, level shifting, electrical isolation, OpenOCD
adapter, programming algorithm and multiple Sites are **not implemented**.
An SWD sequence can later compose transmit/Hi-Z/receive commands,
but must meet the official ARM timing/electrical requirements first.

Do **not** connect DUT signals, reprogram Z2 or load this RTL into an active
FPGA on the basis of these tests. A future source-controlled Vivado Block
Design, implemented timing, HWH, clock/reset handoff, recovery plan and
electrical qualification are mandatory before physical HIL.

## Reproducible host-only validation

```bash
python3 -m pytest -v pl/verification/test_pspl02_swd00_rtl.py
verilator --lint-only --sv -Wall -Wno-UNUSEDSIGNAL \
  --top-module pl_control_axi_lite pl/rtl/bus/pl_control_axi_lite.sv
verilator --lint-only --sv -Wall -Wno-UNUSEDSIGNAL \
  --top-module swd_waveform_engine pl/rtl/site/swd_waveform_engine.sv
```

Simulator dependencies match the existing PL CI: Icarus, Cocotb 1.9.2,
Cocotb-test 0.2.6 and pytest. The new PR workflow executes the same checks.

## Remaining milestones

1. Get Verilator/Cocotb regressions passing in PR CI.
2. Source-controlled Vivado Block Design with separate Identity and Control
   apertures, plus an AXI-visible SWD command interface in a later scoped step.
3. Run SWPC Vivado 2026.1 synthesis, implementation, timing, bitstream and
   artifact provenance checks in an isolated worktree.
4. Separately approve and execute Z2 FPGA loading and PS-to-PL read/write HIL.
5. Separately qualify SWDIO turnaround, pin voltage/safety, real SWD target.

None of steps 2–5 are qualified by merging this RTL source candidate.
