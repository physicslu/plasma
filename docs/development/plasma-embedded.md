# PLASMA — Embedded / PPU Engineering Contract

> Domain-specific contract. Read with [AGENTS.md](../../AGENTS.md) and [Common](plasma-development-common.md) for Z2 Linux, PS runtime, OpenOCD and device operations.

## Scope
- Z2 Linux, PS runtime, native OpenOCD, WordPort/Remote Bitbang, PS drivers, MMIO, PPU services, hardware ownership and recovery.
- Live OpenOCD and bit-level SWD execution belong on Z2 PS, not SWPC. PL performs the DUT electrical interface.
- Before any real hardware action verify current boot/source, paired image identity, permissions, owner/lease, electrical conditions and Golden recovery.
- Keep credentials private; no privilege escalation or sudoers changes. Use actual Linux permissions and protected Root guards.
- Changes to PL registers or ABI also load [FPGA](plasma-fpga.md). Changes to Gateway/Manager-facing API also load [Manager](plasma-manager.md).
- Record authentic PASS/FAIL/NOT_RUN; host-only tests cannot establish real programming qualification.

## Migrated detailed clauses from shared contract

## 17. Z2 production direction

Z2 is the intended embedded PPU controller/runtime, not a clone of the integration workstation.

Expected runtime responsibilities, subject to validation:

```text
Embedded Linux
Python Plasma runtime
PYNQ / FPGA runtime
Plasma Server / API layer
FPGA bitstream + HWH
configuration / target definitions
production Web assets or selected Web runtime
system services
logs / diagnostics
```

Development-only components such as Vivado, pytest, npm build tooling, source-control credentials, and developer SSH keys should not automatically be included in a production image.

Before standardizing a Z2 Python environment, verify compatibility with PYNQ/XRT first.
