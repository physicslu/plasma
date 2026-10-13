# STM32F103 Manufacturer-Derived Programmer Codegen Pilot

Status: research / software-only

## Purpose

This pilot tests whether Plasma can generate a mechanically checkable STM32F103 Flash-programming implementation from manufacturer-derived canonical knowledge and only afterward compare the generated semantics with an independent OpenOCD implementation reference.

The experiment is deliberately asymmetric. OpenOCD may validate or challenge a generated result, but OpenOCD must not supply constants, limits, geometry, control flow, or policy to the generator.

## Trust chain

The generation path is:

ST manufacturer evidence
-> frozen STM32F103C8T6 manufacturer baseline
-> manufacturer-derived Programming Profile
-> validated Programming Execution IR
-> generate_stm32f103_programmer.py
-> ephemeral generated Python reference programmer

The generated reference is then validated independently by fake Flash-controller behavioral tests and a post-generation OpenOCD differential validator.

Generation inputs are:

- data/ic-support/manufacturer-baseline/stm32f103c8t6-manufacturer-only-v1.json
- data/ic-support/profiles/programming/stm32f1-medium-density-flash-v0.json
- data/ic-support/execution-ir/stm32f103c-programming-execution-ir-v0.json

The frozen baseline owns exact-device identity and geometry. The Programming Profile supplies manufacturer-evidenced numeric register and bit encodings that the original frozen baseline intentionally does not duplicate. The Execution IR supplies validated execution semantics and safety invariants. The generator verifies that these inputs agree before emitting code.

OpenOCD files and the post-freeze OpenOCD comparison record are not generator inputs.

## Generated v1 surface

The generated reference programmer contains software-only implementations of:

- Flash busy polling with a caller-supplied poll budget;
- Flash unlock with terminal read-back;
- Flash lock with terminal read-back;
- 16-bit Main Flash programming;
- explicit PGERR and WRPRTERR observation;
- read-back verification;
- 1-KiB page erase and erase verification;
- Main Flash mass erase with an explicit authorization barrier;
- exact STM32F103C8T6 Main Flash range enforcement.

The generator intentionally does not create a default timeout, adapter speed, target-halted requirement, RAM loader, Blue Pill 128-KiB override, clone compatibility rule, RDP transition, Option Byte workflow, or physical runtime enablement.

max_polls is a caller-supplied execution-policy value. It is not presented as a manufacturer timing limit.

## Failure-state rule

An unresolved FLASH_SR.BSY timeout produces an uncertain controller state. Generated code therefore does not execute normal mode-bit cleanup after such a timeout. This preserves the existing Execution IR safety invariant instead of pretending the target returned to a known idle state.

## OpenOCD differential

compare_generated_programmer_openocd.py is strictly post-generation. It compares generated semantics with the pinned OpenOCD v0.12.0 review record tied to source commit 9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c.

The differential requires agreement on:

- unlock keys;
- Flash status-bit identities;
- medium-density 1-KiB page size;
- 16-bit programming alignment;
- page-erase core semantics;
- mass-erase core semantics;
- programming core semantics.

It separately proves that backend-only behavior remains separated:

- OpenOCD RAM loader remains an optimization, not a device requirement;
- target-halted behavior remains backend policy;
- OpenOCD software timeout values do not become manufacturer limits;
- the 1-MHz adapter default does not become a manufacturer SWD/JTAG clock value;
- the Blue Pill 128-KiB board override cannot change exact STM32F103C8T6 64-KiB geometry.

This is semantic differential validation against a source-pinned OpenOCD review record. It is not a claim that the generated source is textually equivalent to stm32f1x.c.

## Validation

CI generates the reference programmer into RUNNER_TEMP, compiles it, runs the fake-controller regressions, runs the OpenOCD semantic differential, and runs differential negative tests.

The generated file is ephemeral by design. It is derived output, not a second checked-in source of truth.

## Qualification boundary

A PASS proves only:

manufacturer-derived inputs
-> deterministic code generation
-> Python compilation
-> fake-controller behavior
-> source-pinned OpenOCD semantic differential

It does not prove OpenOCD process execution, SWD/JTAG electrical behavior, ST-Link or another physical adapter, PYNQ-Z2, FPGA/PL, target power/reset sequencing, a real STM32F103C8T6, RDP/Option Byte behavior, or physical programming qualification.

hardware_runtime_ready and physical_programming_qualified remain false.
