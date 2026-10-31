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
