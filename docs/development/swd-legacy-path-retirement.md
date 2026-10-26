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

## Remaining legacy HIL entrypoints and live safety dependencies

| Source / entrypoint | Scope and actual capability | Current decision |
| --- | --- | --- |
| `python -m pl.hil.swd04.one_shot` | Historical SWD-05 internal FPGA synthetic fixture load/MMIO/recovery | **DIRECT CLI RETIRED** (`RETIRED_SWD05_INTERNAL_IMAGE_CLI`). Retain importable `run_sequence`, `run_live`, `manager_write`, `OWNER_LOCK` and Root safety helpers for F1-B and existing protected recovery. |
| `python -m pl.hil.swd04.native_qualify` | Historical SWD-04 `/dev/mem` native AXI synthetic DPIDR HIL | **DIRECT CLI RETIRED** (`RETIRED_SWD04_SYNTHETIC_MMIO_CLI`). Retain injected `run_stage` and `check_runtime` for host-only tests and F1-B imports. |
| `pl.hil.swd04.development` | Historical ownership/current loaded-image receipt helpers | **RETAIN guarded helpers**; not an alternate external Blue Pill SWD controller. |
| `pl.hil.pspl02.runner` and `pl.hil.lt02.native` | Separate PS→PL internal loopback/AXI MMIO HIL; NO external SWD pins | **RETAIN for independent internal validation only** with existing safety gates; not a Blue Pill programmer. |
| `pl/projects/z2-fixed-unified-site1/`, `SWDTransactionDriver`, `swd_transaction_master.sv` | Fixed ABI/internal synthetic fixture and future RTL/controller candidates | **RETAIN offline tests/build dependencies**; no automatic live PMOD/DUT qualification. Do not substitute for current WordPort image. |
| `scripts/plasma-z2-smoke.sh` | Separate protected Z2 SSH smoke/diagnostic development utility | **RETAIN guarded maintenance workflow**; not a real SWD programming backend and may not load retired FPGA images. |

The SWD-05 historical no-callback `one_shot.run_live()` execution mode additionally fails **before image preflight/FPGA load**, so retiring its CLI cannot leave an already-loaded synthetic Image when the child CLI is unavailable. F1-B passes an explicit Identity callback and retains protected Root/ownership/recovery admission. Host-only regression verifies both the negative gate and F1-B callback injection.

The direct legacy Python CLI guards prevent ordinary `python -m ...` execution, but **are not an OS privilege boundary**; imported shared functions remain callable and protected by independent Root/ownership/lock controls. Their continued presence does not authorize them as an external target interface. Synthetic DPIDR `0x2BA01477` must never be confused with ST-LINK-observed STM32F103 `0x1BA01477`.

## Operator / Codex selection rule

1. Confirm the actual current Git worktree, SHA and owner-approved Gate 1 hardware scope. Old Worktrees and historical README search hits do not define current architecture.
2. Only select Z2 PS-local ARMv7 OpenOCD, reviewed UNIX WordPort bridge, exact paired PL Image/Manifest and physical PMOD wiring for external MCU; never select either retired project by name or alphabetical order.
3. Require live Z2 Boot ID, Root source SHA and manifest, FPGA Manager load/current image/owner-lock/MMIO lease, validated Golden recovery and legal 3.3V/common-ground/no competing SWD driver. LA2016 passively observes signal only.
4. 2026-10-23 ST-LINK true successful Golden DPIDR `0x1BA01477` is independent reference. SWD-03 synthetic `0x2BA01477` is **not** the real DUT. Record fresh `.sr` capture and local OpenOCD/WordPort command exits; absent physical evidence is NOT_RUN, even if GitHub job exits zero.
5. Retained shared code exists only for proven imports and host regressions; migrate those consumers before future physical deletion. Do not conflate retirement of old **Image selection** with deletion of shared FPGA safety locks or `one_shot` code.
