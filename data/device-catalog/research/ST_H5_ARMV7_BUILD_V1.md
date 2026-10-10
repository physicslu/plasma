# STM32H5 OpenOCD ARMv7 isolated build v1

Status: **research-only experimental CI**. Follows host build PR #793; the branch is based on PR #793 and targets that branch to avoid requiring its merge.

## Objective

Compile the ST OpenOCD fork at immutable commit `c8d973bdad9a6fddb51459eda109b3b95d23b57a` inside **QEMU-emulated 32-bit ARMv7 Ubuntu 22.04 userspace** (not x86 cross-compiled and not Z2 native). Keep the binary, its installed Tcl scripts and the packaging tarball in the ephemeral CI container. Upload only machine-readable, non-hardware evidence.

The experiment checks:
1. actual `uname -m=armv7l` and fixed ST source/file blob identity;
2. build + install including H5 native Flash driver source;
3. `openocd --version`, dummy JTAG `target/stm32h5x.cfg` syntax/config load with no `init` or physical adapter;
4. `scripts/openocd-runtime.py build` with `--architecture armv7l`, `verify`, matching artifact digests and explicit `hardware_runtime_ready=false`.

## Limits

**Emulated ARMv7 execution is not Z2 PS hardware evidence.** Container emulation does not verify PYNQ-Z2 OS/library versions, target memory, FPGA PL, SWD transport, electrical programming profiles, or an H5 physical target. Dummy adapter supports JTAG-only; its successful configuration parse says nothing about the FPGA SWD adapter. Future gates remain: Z2 ABI/library and native runtime validation; SWD transport adapter implemented and tested; controlled read-only physical die-ID probe; then separately authorized erase/program/verify.

The workflow neither deploys nor modifies the existing `/opt/plasma/programming-engines/openocd` runtime and makes **no Production Catalog changes**. No OpenOCD binary or archive is uploaded or distributed; independently review GPL compliance before release.

## Operational decision

Do **not merge this experiment** solely on emulated compilation. Confirm complete CI, generated evidence checksum, absence of accidental runtime output uploads, and downstream PR #793 disposition. Review/approval is required before merging.

The current Production baseline remains 4,629 exact identities, 4,164 mapped, 465 no_mapping. The 190 H5 and 172 C5 stay blocked.
