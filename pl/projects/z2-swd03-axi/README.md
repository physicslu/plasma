# RETIRED — Z2 SWD-03 AXI Internal Synthetic DPIDR Fixture

**RETIRED for physical Blue Pill SWD and new Vivado FPGA image builds.** Archived execution and staging instructions in older Git history must never be selected for Path 3 HIL.

SWD-03 connects an AXI4-Lite transaction engine to an **internal synthetic SWD target**. There are **no external PMOD SWD pins**. Its fabricated DPIDR is `0x2BA01477`; the archived real STM32F103 ST-LINK trace observes `0x1BA01477`. Fixture ACK/DPIDR PASS cannot prove Blue Pill connectivity, voltage, programming, OpenOCD or Flash.

Current external MCU path: root [AGENTS.md](../../../AGENTS.md) → Z2 PS-local ARMv7 OpenOCD → UNIX WordPort/RemoteBitbang → verified PL SWD Image → PMOD → Blue Pill. See [retirement inventory](../../../docs/development/swd-legacy-path-retirement.md), [PS bridge](../../../scripts/bluepill-wordport-session.py) and [Image Manifest](../z2-bluepill-rbb/image-manifest.json).

**Fail-closed:** legacy `build-on-swpc.sh`, project Tcl and standalone `artifact.py` CLI reject use with `RETIRED_Z2_SWD03_AXI`. Retained RTL `swd03_dpidr_responder.sv`, shared source and importable Python helpers remain only for internal synthetic regression and dependent tests. Never delete actual FPGA Root Guard/lock/Golden recovery code merely because historic filenames mention SWD-04/05.
