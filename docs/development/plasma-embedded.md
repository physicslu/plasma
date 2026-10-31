# PLASMA — Embedded / PPU Engineering Contract

> Domain-specific contract. Read with [AGENTS.md](../../AGENTS.md) and [Common](plasma-development-common.md) for Z2 Linux, PS runtime, OpenOCD and device operations.

## Scope
- Z2 Linux, PS runtime, native OpenOCD, WordPort/Remote Bitbang, PS drivers, MMIO, PPU services, hardware ownership and recovery.
- Live OpenOCD and bit-level SWD execution belong on Z2 PS, not SWPC. PL performs the DUT electrical interface.
- Before any real hardware action verify current boot/source, paired image identity, permissions, owner/lease, electrical conditions and Golden recovery.
- Keep credentials private; no privilege escalation or sudoers changes. Use actual Linux permissions and protected Root guards.
- Changes to PL registers or ABI also load [FPGA](plasma-fpga.md). Changes to Gateway/Manager-facing API also load [Manager](plasma-manager.md).
- Record authentic PASS/FAIL/NOT_RUN; host-only tests cannot establish real programming qualification.
