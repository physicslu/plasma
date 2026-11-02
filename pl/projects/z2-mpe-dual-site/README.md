# Historical composite-MPE Vivado prototype — **NOT FINAL, DO NOT BUILD OR DEPLOY**

> **Owner architecture update 2026-10-27:** [ADR-0005](../../../docs/adr/0005-independent-swd-ip-guarded-bitbang.md) replaces the composite MPE control topology with **two separately addressable standalone AXI SWD IP instances** behind standard PS7 AXI Interconnect. Normal SWD FSM and optional Controlled Bitbang are mutually exclusive per Site. The Debug OpenOCD SWD remote_bitbang bridge is **BLOCKED** until source/build-version qualification; existing OpenOCD 0.12.0 has JTAG-only remote_bitbang.

The `plasma_mpe_*` RTL, `create_project.tcl` and `create_block_design.tcl` stored here are **migration/source-only candidates** and not approved production inputs. No complete `build_bitstream.tcl`, qualified SWPC Path 2 `operator-cli` entrypoint, signed-off HWH verifier, BIT/BIN, loaded Image or true target DPIDR evidence exists for this project.

Do not run this provisional Project Tcl as a final engineering build, use it to deploy to the Z2, or infer two independent AXI IP instances from its single composite slave. Preserve prior simulator results as **historical candidate evidence only**; they do not qualify the new architecture. Keep installed Image, Root Guard and Golden Recovery unaffected.

The successor Project will own two distinct register apertures and SWD IP modules, all pins/clock/reset constraints, host-only simulation and real Vivado timing/DRC/HWH identity checks. The approved SWPC Build execution method is [ADR-0004](../../../docs/adr/0004-project-isolated-fpga-build-path2-operator-cli.md), Path 2 `operator-cli`; no automatic FPGA download.
