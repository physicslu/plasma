# Profile-driven OpenOCD Plan Compiler

Status: **Phase 3.7 current contract**

## 1. Purpose

Phase 3.7 converts evidence-backed IC Support knowledge into a deterministic, reviewable OpenOCD dry-run execution plan without starting OpenOCD or touching hardware.

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
  -> runtime-readiness gate
  -> STOP: no hardware executor in Phase 3.7
```

This phase proves the transformation from support knowledge to backend-specific command intent. It does not prove that those commands successfully program a physical IC.

## 2. Current supported scope

The compiler supports only the evidence-backed Programming Profile:

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

This is the first concrete proof that Plasma can reuse one Programming Profile across multiple exact ICPNs while varying geometry independently.

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

Artifact references are symbolic tokens, not filesystem paths. For example:

```text
${PLASMA_IMAGE_BIN}
${PLASMA_READ_000_BIN}
```

The compiler does not create staging files and does not infer a client-supplied path.

## 4. Operation compilation

### 4.1 ERASE

Phase 3.7 ERASE means full resolved Main Flash erase.

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

The symbolic input artifact is bound to the Job's image size and SHA-256.

PROGRAM does not implicitly erase in Phase 3.7. ERASE and PROGRAM remain separate Plasma operations.

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

The default dry-run reads the first 256 bytes of resolved Main Flash:

```text
init
reset init
dump_image ${PLASMA_READ_000_BIN} 0x08000000 0x00000100
shutdown
```

Option Bytes, OTP, system memory and other address spaces are deliberately outside this Phase 3.7 Main Flash plan compiler.

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

Phase 3.7 changes route state from:

```text
routing_only
```

to:

```text
plan_compiled_not_executable
```

for supported OpenOCD routes.

The route contains the dry-run plan, but still records:

```text
hardware_runtime_ready = false
```

and `SiteManager` rejects the real Job before JobRegistry insertion, PPU lease reservation, SiteWorker queueing or interface execution.

`OpenOCDInterface.erase/program/verify/read` also fail closed until a validated compiled-plan executor exists. The previous direct hard-coded 64 KiB erase path is removed, so there is no alternate target-specific command path around the compiler.

## 7. OpenOCD command basis

The command forms used by this compiler follow the OpenOCD User's Guide:

- Flash Commands: <https://openocd.org/doc/html/Flash-Commands.html>
- Flash Programming: <https://openocd.org/doc/html/Flash-Programming.html>
- General Commands / image access: <https://openocd.org/doc/html/General-Commands.html>

The relevant upstream behavior includes:

- use `reset init` before Flash Programming Commands;
- `flash erase_address address length` erases a resolved address range;
- `flash write_image filename offset type` writes an image without requiring implicit erase;
- `flash verify_image filename offset type` performs flash-driver-aware verification;
- `dump_image filename address size` emits a memory range to a binary file.

These upstream command definitions do not substitute for physical STM32F103 validation. They only establish the backend command grammar used by the dry-run compiler.

## 8. Coverage meaning after Phase 3.7

The production catalog baseline remains unchanged:

```text
Exact ICPNs:                              124
Base Devices:                              32
Evidence-backed Programming Profiles:       1
OpenOCD plan-compiled Programming Profiles:  1
OpenOCD plan-compiled exact ICPNs:           2
Native PPU runtime-ready exact ICPNs:        0
```

The new `1` means a profile has a deterministic backend plan compiler. It does not mean physical programming has passed.

## 9. Next gate

The next phase may introduce a controlled executor that consumes `OpenOCDExecutionPlan`, stages artifacts safely and validates the plan first against software/process behavior and then against real STM32F103 hardware.

Hardware readiness must remain a separate, evidence-backed state transition. It must never be inferred merely because a command plan can be generated.

## 10. Non-goals

Phase 3.7 does not:

- add new exact ICPNs;
- create STM32F4 Programming Profiles;
- execute OpenOCD programming commands;
- create image staging files;
- alter PMode / EMode IC selection;
- implement Native PPU programming;
- create PPU or Socket verification evidence;
- deploy or restart services;
- access Z2, FPGA or real IC hardware.
