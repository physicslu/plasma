# SWD Legacy Path Retirement — Current Blue Pill Selection & Dependencies

**2026-10-26 decision.** For real external STM32 Blue Pill SWD select **Z2 PS-local OpenOCD -> PS-local UNIX WordPort/RemoteBitbang -> verified PL SWD Image -> PMOD SWCLK/SWDIO -> Blue Pill**. This is a source-selection invariant, not a fresh HIL PASS or hardware authorization. Retirement base: `0c11e3420272bed09e778182e9d6422c115f75d0`.

| Item | Status | Required distinction / dependency |
| --- | --- | --- |
| `pl/projects/z2-swd-gpio/` | **RETIRED physical FPGA project** | PS EMIO GPIO software bit-bang, not current PL SWD. Build, monitor, Tcl, standalone artifact CLI fail closed. |
| `pl/projects/z2-swd03-axi/` | **RETIRED physical FPGA project** | FPGA-internal synthetic responder (DPIDR `0x2BA01477`); no external SWD pins. Build, Tcl and standalone artifact CLI fail closed. |
| `pl/projects/z2-swd-gpio/artifact.py` | Shared **host-only** imports | Used by `z2-identity/artifact.py` and `z2-control-waveform/artifact.py` for identity headers, git/hash generation. Standalone CLI blocked; do not delete dependency blindly. |
| `pl/projects/z2-swd-gpio/prepare-board-repository.sh` | Shared generic Board Files helper | Needed by trusted `scripts/plasma_vivado_host_build.py` and Vivado environment preflight. It does not build or load retired FPGA images. |
| `pl/projects/z2-swd-gpio/check-swpc-vivado-runner.sh` / `probe-vivado.tcl` | Generic **read-only Vivado** probe | Called by `swpc-vivado-runner-environment.yml`. Not a programmer/hardware-load contract. |
| `pl/rtl/site/swd_emio_bridge.sv` and old GPIO XDC | Historical RTL / offline source tests | Not production external SWD. |
| `pl/rtl/site/swd03_dpidr_responder.sv`, `pl/sim/swd03_axi_fixture_tb.sv` | **SYNTHETIC-only** RTL/fixture | Used by SWD-03/04/06, LT02 and Fixed ABI host regressions. Never treat synthetic ACK/data as Blue Pill. |
| `pl/hil/swd04/`, SWD-05 source and `docs/development/swd04-*` | Historical **internal HIL** contracts | Some Root/target guard code still imports `pl/hil/swd04/one_shot.py` safety/owner-lock helpers. Do not delete locks, Root Guard, FPGA Manager safety or Golden recovery. |
| `pl/projects/z2-fixed-unified-site1/` | Separate fixed-ABI host candidate/internal fixture | Does not automatically represent the current external Blue Pill image. |
| `pl/projects/z2-bluepill-rbb/image-manifest.json`, `scripts/bluepill-wordport-session.py` | **Current selected Path 3 PoC source path** | Paired PL Image identity + PS-local WordPort bridge; still verify live boot/manager/ownership and real SWD before PASS. |
| `.github/workflows/swpc-vivado-bitstream-build.yml` | **REMOVED** | Manual persistent-runner action targeting old GPIO Image should not be offered. |
| `.github/workflows/pl-z2-swd-gpio.yml`, `pl-swd03-axi.yml` | Offline regression only | Keep hosted PR/main tests for shared/fixture source; remove manual dispatch. No physical target qualification. |

## Operator / Codex selection rule

1. Confirm the actual current Git worktree, SHA and owner-approved Gate 1 hardware scope. Old Worktrees and historical README search hits do not define current architecture.
2. Only select Z2 PS-local ARMv7 OpenOCD, reviewed UNIX WordPort bridge, exact paired PL Image/Manifest and physical PMOD wiring for external MCU; never select either retired project by name or alphabetical order.
3. Require live Z2 Boot ID, Root source SHA and manifest, FPGA Manager load/current image/owner-lock/MMIO lease, validated Golden recovery and legal 3.3V/common-ground/no competing SWD driver. LA2016 passively observes signal only.
4. 2026-10-23 ST-LINK true successful Golden DPIDR `0x1BA01477` is independent reference. SWD-03 synthetic `0x2BA01477` is **not** the real DUT. Record fresh `.sr` capture and local OpenOCD/WordPort command exits; absent physical evidence is NOT_RUN, even if GitHub job exits zero.
5. Retained shared code exists only for proven imports and host regressions; migrate those consumers before future physical deletion. Do not conflate retirement of old **Image selection** with deletion of shared FPGA safety locks or `one_shot` code.
