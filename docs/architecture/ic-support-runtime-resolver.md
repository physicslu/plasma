# IC Support Runtime Resolver and Execution Binding

Status: **Current route-resolution and execution-admission contract; introduced in Phase 3.6 and extended by the OpenOCD planning/executor phases**

## 1. Purpose

Plasma resolves an exact commercial IC part number into reusable technical support knowledge before a real Programming Site is allowed to queue work.

The current chain is:

```text
Exact ICPN
  -> Device Catalog identity
  -> IC Support binding
  -> ResolvedICSupport
  -> SiteExecutionRouter
       -> resolve route
       -> compile backend plan where supported
       -> backend-runtime readiness gate
  -> execution admission
  -> RoutedProgrammingHandler
  -> selected Site interface
```

`ResolvedICSupport` is not a support badge and is not physical validation. It is the deterministic join between one exact ICPN and reusable Programming, Memory Geometry, Package / Hardware, Option and Security profiles owned by `data/ic-support/`.

A route or command plan being deterministically resolvable is not sufficient for execution admission. The selected backend implementation must separately be runtime-ready.

## 2. Current production knowledge baseline

The executable production baseline is:

```text
Exact ICPNs:                           286
Families:                                2
  STM32F1:                              75
  STM32F4:                             211
Base Devices:                           91
Deterministic OpenOCD-mapped ICPNs:    286
Direct IC Support-bound ICPNs:           2
Unresolved Programming Profile ICPNs:  284
Evidence-backed Programming Profiles:    1
OpenOCD plan-compiled Profiles:           1
OpenOCD plan-compiled exact ICPNs:        2
Native PPU runtime-ready exact ICPNs:     0
```

The two directly resolvable exact ICPNs are:

```text
STM32F103C8T6
STM32F103CBT6
```

They share:

```text
Programming Profile: stm32f1-medium-density-flash-v0
OpenOCD target:       tcl/target/stm32f1x.cfg
```

but intentionally use different Memory Geometry Profiles for 64 KiB and 128 KiB Main Flash.

An admitted catalog part such as `STM32F407VGT6` remains unresolved by the IC Support runtime resolver. Its deterministic OpenOCD target mapping is catalog/backend evidence, not proof of a complete Programming Profile.

The production counts above are derived from the production Device Catalog and enforced by `data/ic-support/test_coverage_inventory.py`. Historical admission documents retain the counts that were true at their own checkpoints.

## 3. Resolver contract

`software/python/plasma_core/ic_support.py` loads checked-in IC Support profile and binding sets and resolves exact ICPNs case-insensitively.

The resolver fails closed on malformed or contradictory checked-in support data, including duplicate identities, missing required fields, dangling or wrong-kind profile references, and malformed Revision Overrides.

A successful `ResolvedICSupport` contains:

```text
exact ICPN
binding set identity/status
expected catalog identity
Programming Profile
Memory Geometry Profile
Package / Hardware Profile
Option Profile
Security Profile
Revision Overrides[]
OpenOCD target identity
```

## 4. Route resolution, plan compilation and execution admission

`software/python/plasma_server/execution_router.py` owns the runtime bridge from IC Support knowledge to execution. It deliberately separates three decisions:

```text
resolve support
    -> Can Plasma deterministically resolve ICPN and reusable profiles?

compile backend plan
    -> Can the selected backend derive deterministic operation intent?

admit execution
    -> Is that backend implementation actually runtime-ready now?
```

For every real non-Mock Job, these decisions happen before:

```text
JobRegistry insertion
PPU execution-lease reservation
SiteWorker queue insertion
hardware/interface execution
```

Therefore neither an unsupported target nor a resolved-but-unimplemented backend can create a phantom queued Job, acquire PPU ownership, or touch hardware.

### 4.1 Mock Site

Mock is a workflow simulator. It may execute any selected production-catalog ICPN without an IC Support binding.

Server-owned route metadata records:

```text
mode: mock_workflow
hardware_support_claimed: false
workflow_runtime_ready: true
hardware_runtime_ready: false
```

Mock success never creates real programming-support evidence. `workflow_runtime_ready` must not be interpreted as hardware or algorithm readiness.

### 4.2 OpenOCD Site

OpenOCD route resolution requires:

1. exact `JobRequest.target` resolves through `ICSupportResolver`;
2. the resolved Programming Profile has a registered OpenOCD plan compiler;
3. the Site's configured `target_cfg` matches the resolver-owned OpenOCD target identity after deterministic path normalization;
4. the Programming and Memory Geometry profiles are internally consistent;
5. operation-specific inputs fit the resolved Main Flash boundary.

The current compiler supports:

```text
stm32f1-medium-density-flash-v0
```

and resolves its target to:

```text
target/stm32f1x.cfg
```

A mismatch such as an F103 ICPN with `target/stm32f4x.cfg` is a configuration error and fails before the runtime-readiness gate.

Equivalent OpenOCD target path forms are normalized, for example:

```text
tcl/target/stm32f1x.cfg
target/stm32f1x.cfg
/usr/share/openocd/scripts/target/stm32f1x.cfg
```

The production route still records:

```text
backend_implementation_state: plan_compiled_not_executable
hardware_runtime_ready: false
```

The server can attach a canonical `openocd_execution_plan` to the route, and the isolated software executor can validate that plan against a fake process. That software validation is not execution authorization for a physical target.

See [Profile-driven OpenOCD Plan Compiler](ic-support-openocd-plan-compiler.md) and [OpenOCD Compiled-Plan Executor](ic-support-openocd-plan-executor.md).

### 4.3 Plasma Native / FPGA Site

A resolvable F103 target can produce a deterministic Plasma Native route identity, but the current contract records:

```text
mode: plasma_native
backend_implementation_state: not_implemented
hardware_runtime_ready: false
```

and rejects the Job before queue admission. No Native PPU runtime consumes the Programming Profile for real programming yet.

Therefore:

```text
Programming Profile resolved
    !=
backend plan compiled
    !=
software executor validated
    !=
backend hardware runtime implemented
    !=
physical PPU / Socket verified
```

## 5. Handler ownership

`SiteManager` does not construct `STM32F103Handler` unconditionally for every enabled Site.

The runtime separates:

```text
ProgrammingOperationHandler
    generic Erase / Program / Verify / Read stage dispatch

SiteExecutionRouter
    target identity / IC Support / backend route resolution
    + backend plan compilation
    + backend-runtime readiness admission

RoutedProgrammingHandler
    preserves SiteWorker's one-handler lifecycle and selects
    an already-admitted Programming Profile handler per Job
```

`STM32F103Handler` remains only as a compatibility alias for older code/tests. It is no longer the SiteManager execution-selection authority.

Programming Profile identity, not commercial ordering suffix, is the reusable execution-selection unit.

## 6. Server-owned resolution metadata

Route identity is carried in server-owned `resolved_ic_support` metadata. Clients may not provide this field. A caller-supplied value is rejected as `INVALID_ARGUMENT` rather than trusted or silently overwritten.

This prevents a client from claiming a different Programming Profile, backend route, compiled plan or readiness state than the server derived from checked-in IC Support data.

## 7. Remaining hardware implementation boundary

The legacy direct hard-coded 64 KiB erase path is removed. `OpenOCDInterface.erase/program/verify/read` remain fail-closed for production hardware use while the production hardware runtime gate is disabled.

The plan compiler and isolated executor now validate deterministic command intent, artifact staging, subprocess isolation, timeout/cancellation cleanup and output collection in software. Remaining hardware work includes:

- selecting and validating the actual OpenOCD installation and adapter configuration on the PS runtime host;
- validating target detection, reset/halt and finalization behavior;
- validating erase/program/verify/read on known STM32F103 hardware;
- consuming Option and Security profiles for non-Main-Flash operations;
- creating independent PPU and Socket validation evidence;
- implementing and validating a separate Plasma Native PS-to-PL programming path.

Because `hardware_runtime_ready=false`, no compiled programming command can enter production hardware execution through resolver-driven admission.

## 8. Scientific scale-out gate remains in force

The STM32F103C IC Support architecture still requires valid evidence before bulk creation of new family Programming Profiles. Catalog expansion alone does not authorize profile inference.

The intended sequence remains:

1. deterministic exact ICPN identity;
2. evidence-backed reusable IC Support profiles;
3. deterministic backend route resolution;
4. deterministic backend plan compilation;
5. controlled software executor validation;
6. backend hardware execution implementation;
7. runtime-readiness admission;
8. software/hardware validation;
9. PPU and Socket evidence as independent dimensions.

This prevents catalog coverage, route resolution, plan generation and actual programming capability from collapsing into one misleading `supported=true` flag.

## 9. Non-goals

The current resolver contract does not:

- infer Programming Profiles for the 284 unresolved production exact ICPNs;
- promote deterministic OpenOCD mapping to programming-profile support;
- make production OpenOCD programming hardware-ready;
- implement a Native PPU programming driver;
- change PMode / EMode IC selection behavior;
- create PPU or Socket validation evidence;
- deploy or restart services;
- access Z2, FPGA or real IC hardware.
