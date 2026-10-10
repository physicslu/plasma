# STM32H5 pinned ST OpenOCD ARMv7 build experiment v1

**State:** research-only ARMv7 build/runtime experiment. No Production mapping or deployed PPU runtime is changed.

## Purpose

Qualify whether the exact pinned ST OpenOCD source commit `c8d973bdad9a6fddb51459eda109b3b95d23b57a` can be built, packaged, installed and executed inside the same Linux ARMv7 userspace class used by PLASMA Z2 qualification.

The workflow uses QEMU/binfmt with `arm32v7/ubuntu:22.04`, verifies the frozen `stm32h5x.cfg`, `stm32h5x.c` and driver-registry Git blobs, builds the H5-capable fork, packages it through the existing PLASMA OpenOCD artifact contract, installs that package on a fresh ARMv7 userspace and parses `target/stm32h5x.cfg` using the dummy JTAG adapter.

## Evidence boundary

A PASS proves only:

- the pinned H5-capable fork compiles for ARMv7;
- the PLASMA artifact packager/verifier accepts the generated ARMv7 payload;
- a fresh ARMv7 userspace can install and execute that package;
- the H5 target Tcl script and H5 flash driver can be loaded far enough for an offline dummy-JTAG parse.

It does **not** qualify the future FPGA SWD adapter, real PYNQ-Z2 electrical path, IDCODE readback, flash erase/program/verify, Programming Profile, Electrical Programming Profile, security/option-byte operations, eight-Site hardware concurrency, or Production route promotion.

The workflow intentionally uploads only JSON evidence. It does not publish or redistribute the built ST-fork binary/archive.

## Next gate

After PASS, the next meaningful gate is the actual PLASMA SWD transport binding plus an approved read-only physical H5 identification/flash-bank probe. Physical mutation remains prohibited until electrical/profile prerequisites are verified.

## Pull-request execution

This experiment is executed by draft PR #794. A PR-synchronize event is intentionally used so the newly added workflow is evaluated from the proposed branch before any merge.
