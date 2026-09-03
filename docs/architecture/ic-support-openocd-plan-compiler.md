# Profile-driven OpenOCD Plan Compiler

Status: **Current deterministic OpenOCD plan-compilation contract; introduced in Phase 3.7**

## 1. Purpose

Plasma converts evidence-backed IC Support knowledge into a deterministic, reviewable OpenOCD execution plan without treating plan generation as hardware readiness.

The current chain is:

```text
Exact ICPN
  -> Device Catalog
  -> IC Support Resolver
  -> ResolvedICSupport
       -> Programming Profile
       -> Memory Geometry Profile
       -> OpenOCD target identity
  -> OpenOCDPlanCompiler
  -> OpenOCDExecutionPlan
  -> software executor validation where applicable
  -> runtime-readiness gate
  -> production hardware gate remains closed
```

This contract proves the transformation from support knowledge to backend-specific command intent. It does not prove that those commands successfully program a physical IC.

## 2. Current supported scope

The compiler supports the evidence-backed Programming Profile:

```text
stm32f1-medium-density-flash-v0
```

which is currently reachable from two exact ICPNs:

```text
STM32F103C8T6
STM32F103CBT6
```

They intentionally share one Programming Profile while retaining distinct Memory Geometry Profiles:

| Exact ICPN | Programming Profile | Memory Geometry | Main Flash | Page size |
|---|---|---|---:|---:|
| STM32F103C8T6 | stm32f1-medium-density-flash-v0 | stm32f103c8-64k-v0 | 64 KiB | 1 KiB |
| STM32F103CBT6 | stm32f1-medium-density-flash-v0 | stm32f103cb-128k-v0 | 128 KiB | 1 KiB |

Therefore a full Main Flash erase plan is not a part-number constant. The compiler derives the range from the selected Memory Geometry Profile:

```text
STM32F103C8T6
  flash erase_address 0x08000000 0x00010000

STM32F103CBT6
  flash erase_address 0x08000000 0x00020000
```

This proves that Plasma can reuse one Programming Profile across multiple exact ICPNs while varying geometry independently.

## 3. Plan model

`software/python/plasma_interfaces/openocd_plan.py` owns the pure compiler and plan model.

`OpenOCDExecutionPlan` records at least:

```text
schema_version
plan_kind = openocd_dry_run
exact ICPN
operation
Programming Profile ID
Memory Geometry Profile ID
normalized OpenOCD target config
resolved Main Flash start / size / end
erase granularity
program granularity
ordered OpenOCD command strings
symbolic input/output artifacts
plan_only = true
hardware_runtime_ready = false
```

Artifact references are symbolic tokens, not caller-controlled filesystem paths. For example:

```text
${PLASMA_IMAGE_BIN}
${PLASMA_READ_000_BIN}
```

## 4. Operation compilation

### 4.1 ERASE

ERASE means full resolved Main Flash erase:

```text
init
reset init
flash erase_address <main_flash_start> <main_flash_size>
shutdown
```

The compiler validates that the resolved Main Flash size is aligned to the declared erase granularity.

### 4.2 PROGRAM

PROGRAM requires a non-empty inline Programming Image whose size does not exceed the resolved Main Flash capacity.

```text
init
reset init
flash write_image ${PLASMA_IMAGE_BIN} <main_flash_start> bin
shutdown
```

The symbolic input artifact is bound to the Job's Image size and SHA-256. PROGRAM does not implicitly erase; ERASE and PROGRAM remain separate Plasma operations.

### 4.3 VERIFY

VERIFY requires a non-empty inline reference Programming Image.

```text
init
reset init
flash verify_image ${PLASMA_IMAGE_BIN} <main_flash_start> bin
shutdown
```

VERIFY does not erase or program.

### 4.4 READ

READ uses explicit `map.sections[]` when supplied. Every section must remain fully inside the resolved Main Flash range.

The default plan reads the first 256 bytes of resolved Main Flash:

```text
init
reset init
dump_image ${PLASMA_READ_000_BIN} 0x08000000 0x00000100
shutdown
```

Option Bytes, OTP, system memory and other address spaces remain outside the current Main Flash plan compiler.

## 5. Fail-closed invariants

The compiler rejects at least:

- Job target and `ResolvedICSupport.icpn` mismatch;
- Programming Profile without a registered OpenOCD plan compiler;
- missing OpenOCD `target_cfg`;
- configured OpenOCD target different from resolver-owned target identity;
- inconsistent Main Flash start / size / end geometry;
- page size x page count different from Main Flash size;
- Main Flash size not aligned to erase granularity;
- Programming Profile / Memory Geometry program-granularity disagreement;
- missing Programming Image for PROGRAM / VERIFY;
- Programming Image larger than resolved Main Flash;
- execution-image references being silently treated as local OpenOCD paths;
- READ sections outside resolved Main Flash;
- operations with no compiler contract.

## 6. Execution remains closed

For supported OpenOCD routes the route state is:

```text
backend_implementation_state: plan_compiled_not_executable
hardware_runtime_ready: false
```

The route contains the canonical plan, and the isolated software executor can validate that plan against a controlled subprocess boundary. Production hardware execution remains fail-closed.

`OpenOCDInterface.erase/program/verify/read` do not provide an alternate target-specific hardware path around the compiler/executor gate.

## 7. OpenOCD command basis

The command forms used by this compiler follow the OpenOCD User's Guide:

- Flash Commands: <https://openocd.org/doc/html/Flash-Commands.html>
- Flash Programming: <https://openocd.org/doc/html/Flash-Programming.html>
- General Commands / image access: <https://openocd.org/doc/html/General-Commands.html>

Relevant upstream behavior includes:

- use `reset init` before Flash Programming Commands;
- `flash erase_address address length` erases a resolved address range;
- `flash write_image filename offset type` writes an image without requiring implicit erase;
- `flash verify_image filename offset type` performs flash-driver-aware verification;
- `dump_image filename address size` emits a memory range to a binary file.

These upstream command definitions do not substitute for physical STM32F103 validation.

## 8. Current coverage meaning

The executable production coverage is:

```text
Exact ICPNs:                               286
Base Devices:                               91
Deterministic OpenOCD-mapped exact ICPNs:  286
Direct IC Support-bound exact ICPNs:         2
Unresolved Programming Profile ICPNs:      284
Evidence-backed Programming Profiles:        1
OpenOCD plan-compiled Programming Profiles:  1
OpenOCD plan-compiled exact ICPNs:            2
Native PPU runtime-ready exact ICPNs:         0
```

The single plan-compiled Programming Profile is a deterministic backend-planning capability. It does not mean physical programming has passed. The 286 deterministic target mappings are catalog routing evidence and must not be reported as 286 compiled Programming Profiles.

## 9. Next hardware gate

A separately approved hardware phase may promote the validated plan/executor path to real OpenOCD runtime use only after adapter, target, erase/program/verify/read, reset/finalization, cancellation and evidence-retention behavior are validated against known hardware.

Hardware readiness must remain a separate, evidence-backed state transition. It must never be inferred merely because a command plan can be generated.

## 10. Non-goals

The current compiler contract does not:

- infer Programming Profiles for the 284 unresolved production exact ICPNs;
- create STM32F4 Programming Profiles from target cfg similarity;
- make production OpenOCD Jobs hardware-executable;
- alter PMode / EMode IC selection;
- implement Native PPU programming;
- create PPU or Socket verification evidence;
- deploy or restart services;
- access Z2, FPGA or real IC hardware.
