# ADR-0006 — Independent SWD hardware engines; future universal per-Site GPIO Bus

> **Status: Accepted (owner architecture direction, 2026-10-27); implementation in Draft PR #1189, not deployed.**
> **Supersedes ADR-0005's optional SWD-only Debug Bitbang decision.** Historical ADR-0005 remains available for audit; its Debug proposal is no longer an implementation target.
> **Gate 1 scope:** remove SWD-only Debug RTL/API/tests from the current independent SWD IP, document the future universal GPIO Bus only. No GPIO Bus implementation, no other protocol engine, no hardware access, no deployment and no merge.

## Approved architecture

- **One PPU, independent Sites:** current PYNQ-Z2 proof-of-concept instantiates two independent SWD AXI4-Lite IPs via a conventional AXI Interconnect; the product roadmap targets up to eight Sites. Each SWD Site owns its own transaction FSM, SWCLK divider, SWDIO turnaround, command/response FIFO, IRQ, error and abort. No global MPE manager or cross-Site SWD bit scheduler.
- **Dedicated SWD IP is NORMAL-only:** FPGA performs complete DP/AP/SWJ/line-reset transactions. OpenOCD's future native SWD adapter submits transaction commands and consumes tagged responses. Linux must not bitbang SWCLK per edge in the formal SWD programming path.
- **No SWD-only Debug Bitbang Mode:** remove `MODE=2`, the `DEBUG_DRIVE`/`DEBUG_SAMPLE` AXI registers, any debug pad multiplexing and the new SWD-specific Python debug bitbang/socket modules from the Draft #1189 source. Keep only **OFF=0** and **NORMAL=1** as explicit mutually guarded output states. For backward-fail-closed behavior, removed offsets `0x3C/0x40` and mode values `2,3,...` must return AXI `SLVERR`; no alternative driver may toggle the dedicated SWD pads.
- **Breaking Site hardware ABI:** candidate identity becomes `0x00050001/0x00050002`. Driver probe must reject previous v4/v3/v2, not silently reinterpret legacy register maps.
- **Separate future general-purpose GPIO Bus:** generic GPIO output-low, high-impedance, input sampling and waveform generation are future independent Site peripherals, not an implicit or renamed SWD debugging feature. Potential uses include I²C/IIC, custom serial/waveform protocols and engineering diagnostics. GPIO must have its own ABI, resource authorization and HIL before implementation/qualification.
- **Other future protocol engines:** JTAG, SPI, UART and I²C are separate future engines where justified. The existence of these names is NOT implemented support, and electrical compatibility is not equivalent to Programming Provider qualification.
- **Per-Site pin ownership / mux:** each physical pin must have exactly one enabled driver. Cross-protocol transfer requires quiescence, high impedance where appropriate, target power/voltage admission and independent per-Site resource lease. I²C needs open-drain/safe external pull-ups, not arbitrary push-pull repurposing of SWD clock/data. Proposed pin mux must not accidentally introduce non-SWD output enable during this SWD-only milestone.
- **Keep current independent two-site physical constraints:** candidate Site1 `0x43C01000`, Site2 `0x43C02000`, 4-KiB apertures pending exact-HWH confirmation. Preserve Root Guard, single Image/Manifest and Golden recovery. No unrelated PL Runtime, production Provider, or existing historical Blue Pill image changed.

## Status and acceptance

- **Implemented by this Draft:** SWD-only Debug RTL/pad/register/bridge/test removal; OFF/NORMAL isolation, v5 ABI, Host-only regression.
- **Still pending:** production OpenOCD Native C adapter, ARMv7 device-width/barrier and PS7 AXI HIL, external IO timing/DRC, exact-source Vivado Build, live two-DUT SWD and qualified eight-Site/other-protocol/GPIO design.
- **Historical PR #1196:** demonstrates actual older single-Site GPIO-bitbang OpenOCD-to-Blue-Pill programming only. It remains immutable evidence, **not** permission to add that implementation back to the new dedicated SWD IP.
- No assumption that a suitable GPIO Bus or other engine already exists; no default fallback to retired bridges. Changes to physical electrical/hardware operation require their own explicitly covered Gate 1 authority. No Gate 2 merge permission is implied.
