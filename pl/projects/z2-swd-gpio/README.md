# RETIRED — Z2 SWD EMIO GPIO (Historical Only)

**RETIRED for PLASMA physical Blue Pill SWD and future FPGA image builds.** The old README build/load instructions are withdrawn; original details remain in Git history, not current operator procedures.

This variant maps **PS EMIO GPIO software bit-banging** through PL IOBUF to PMOD-B W14/SWCLK, Y14/SWDIO. It is not the current FPGA SWD image driven by Z2 PS-local OpenOCD/WordPort. No historical host tests prove real Blue Pill DPIDR or Flash operations.

**Current physical path:** root [AGENTS.md](../../../AGENTS.md), [retirement dependency map](../../../docs/development/swd-legacy-path-retirement.md), [PS-local bridge](../../../scripts/bluepill-wordport-session.py), and [current Blue Pill PL image Manifest](../z2-bluepill-rbb/image-manifest.json). A Manifest in Git does not prove the Image is currently loaded; require real Z2 hardware ownership, Root Guard, recovery and SWD receipts.

**Fail-closed:** `build-on-swpc.sh`, `run-monitored-on-swpc.sh`, `build-blocking-on-swpc.sh`, project Tcl entrypoints and standalone `artifact.py` CLI reject use with `RETIRED_Z2_SWD_GPIO`. Importable artifact/Identity helpers, pinned Board Files preparation, read-only Vivado probe and host-only tests remain solely for other existing code dependencies. The obsolete persistent SWPC FPGA bitstream build Workflow is removed.

Retirement work does not operate FPGA Manager, LA2016, Z2, Blue Pill or Flash.
