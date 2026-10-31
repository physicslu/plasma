# PLASMA — FPGA / PL Engineering Contract

> Domain-specific contract. Read with [AGENTS.md](../../AGENTS.md) and [Common](plasma-development-common.md) when changing FPGA RTL, constraints, PL images or PS/PL interfaces.

## Scope
- RTL, simulation, synthesis, implementation, timing, XDC, Vivado artifacts, FPGA image/manifest, AXI-Lite/MMIO register maps and PL hardware interfaces.
- Keep the Z2 PS-local OpenOCD -> WordPort -> PL SWD physical architecture; do not reintroduce retired SWD routes.
- Each FPGA BIN must be paired with its Manifest. Check actual SHA256, board/part, ABI, owner, leases and protected Root recovery before authorized hardware loads.
- Successful FPGA Download defaults to Keep Loaded. Do not restore Golden merely because downstream MMIO or DPIDR fails. Unsafe/unknown load or electrical state must fail closed.
- Changes to MMIO/ABI or other PS-facing interfaces also load [Embedded](plasma-embedded.md) and test the affected interface.
- Use genuine Vivado timing/DRC/build evidence where required; simulation and CI never prove real hardware.
- Do not operate Z2/FPGA/DUT without approved scope and applicable guards.

## Migrated detailed clauses from shared contract

## 16. FPGA / PL rules

`pl/` contains FPGA/PL work for Z2. RTL, XDC, register maps, Vivado scripts, bitstreams, and hardware-visible interfaces are contracts.

New production RTL uses SystemVerilog and follows `pl/AGENTS.md`, `docs/development/fpga-development-guide.md`, and `docs/development/fpga-verification-guide.md`.

Canonical repeated programming-resource terminology is **Site**, including `pl/rtl/site/`. Do not create production `channel` modules/directories from retired software vocabulary; use channel only when it genuinely denotes a lower-level protocol/bus concept and document that distinction.

When PL-visible behavior changes:

- check Python/PYNQ register access;
- check register-map documentation;
- check clock/reset/CDC and XDC/timing constraints;
- run appropriate simulation/lint/SVA/cocotb validation;
- do not claim synthesis/implementation/timing/bitstream success unless actually run;
- do not claim Z2 hardware success from software tests.
