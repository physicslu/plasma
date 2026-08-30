# IC Support Runtime Resolver and Execution Binding

Status: **Phase 3.6 current contract**

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
       -> backend-runtime readiness gate
  -> execution admission
  -> RoutedProgrammingHandler
  -> selected Site interface
```

`ResolvedICSupport` is not a support badge and is not physical validation. It is the deterministic join between one exact ICPN and the reusable Programming, Memory Geometry, Package / Hardware, Option and Security profiles owned by `data/ic-support/`.

A route being deterministically resolvable is not sufficient for execution admission. The selected backend implementation must separately be runtime-ready.

## 2. Current production knowledge baseline

The Phase 3.6 baseline remains:

- production Device Catalog: 124 exact ICPNs;
- normalized Base Devices: 32;
- deterministic OpenOCD target mappings: 124;
- direct evidence-backed IC Support bindings: 2;
- evidence-backed Programming Profiles reachable through those bindings: 1;
- Native PPU runtime-ready exact ICPNs: 0.

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

## 3. Resolver contract

`software/python/plasma_core/ic_support.py` loads the checked-in IC Support profile and binding sets and resolves exact ICPNs case-insensitively.

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

## 4. Phase 3.6 route resolution and execution admission

`software/python/plasma_server/execution_router.py` owns the first runtime bridge from IC Support knowledge to execution. It deliberately separates two decisions:

```text
resolve_route(request)
    -> Can Plasma deterministically resolve ICPN, profile and backend identity?

admit(request)
    -> Is that selected backend implementation actually runtime-ready now?
```

For every real non-Mock Job, both decisions happen before:

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
2. the resolved Programming Profile has a registered route identity;
3. the Site's configured `target_cfg` matches the resolver-owned OpenOCD target identity after deterministic path normalization.

At the Phase 3.6 baseline, the only routable Programming Profile is:

```text
stm32f1-medium-density-flash-v0
```

and it resolves to:

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

Phase 3.6 still sets:

```text
backend_implementation_state: routing_only
hardware_runtime_ready: false
```

for the OpenOCD route. Consequently **even a correctly resolved F103 C8/CB Job is rejected before queue admission** until a later phase replaces the incomplete OpenOCD operation templates with profile-driven, tested implementation.

This prevents the current fixed erase template from being executed merely because target/profile identity has been resolved.

### 4.3 Plasma Native / FPGA Site

A resolvable F103 target can also produce a deterministic Plasma Native route identity, but Phase 3.6 records:

```text
mode: plasma_native
backend_implementation_state: not_implemented
hardware_runtime_ready: false
```

and rejects the Job before queue admission. No Native PPU runtime consumes the Programming Profile yet.

Therefore:

```text
Programming Profile resolved
    !=
backend runtime implemented
    !=
physical PPU / Socket verified
```

## 5. Handler ownership

`SiteManager` no longer constructs `STM32F103Handler` unconditionally for every enabled Site.

The runtime now separates:

```text
ProgrammingOperationHandler
    generic Erase / Program / Verify / Read stage dispatch

SiteExecutionRouter
    target identity / IC Support / backend route resolution
    + backend-runtime readiness admission

RoutedProgrammingHandler
    preserves SiteWorker's one-handler lifecycle and selects
    an already-admitted Programming Profile handler per Job
```

`STM32F103Handler` remains only as a compatibility alias for older code/tests. It is no longer the SiteManager execution-selection authority.

Programming Profile identity, not commercial ordering suffix, is the reusable execution-selection unit.

## 6. Server-owned resolution metadata

Route identity is carried in server-owned `resolved_ic_support` metadata. Clients may not provide this field. A caller-supplied value is rejected as `INVALID_ARGUMENT` rather than trusted or silently overwritten.

This prevents a client from claiming a different Programming Profile, backend route or readiness state than the server derived from checked-in IC Support data.

## 7. Remaining OpenOCD implementation boundary

Known implementation debt remains:

- `OpenOCDInterface.erase()` still contains a fixed `0x08000000 / 0x10000` erase template;
- OpenOCD Program / Verify / Read still require hardware-specific implementation;
- Memory Geometry, Option and Security profiles are resolved but are not yet translated into OpenOCD command generation;
- no physical PPU/Socket validation evidence is created by CI.

Because the route is not hardware-runtime-ready, Phase 3.6 does not permit these incomplete commands to be reached through the new resolver-driven admission path.

## 8. Scientific scale-out gate remains in force

The STM32F103C IC Support architecture still requires a valid isolated blind extraction result before bulk creation of new family Programming Profiles. Phase 3.6 does not weaken that gate.

The intended sequence remains:

1. deterministic exact ICPN identity;
2. evidence-backed reusable IC Support profiles;
3. deterministic backend route resolution;
4. backend command/driver implementation;
5. runtime-readiness admission;
6. software/hardware validation;
7. PPU and Socket evidence as independent dimensions.

This prevents catalog coverage, route resolution and actual programming capability from collapsing into one misleading `supported=true` flag.

## 9. Non-goals

Phase 3.6 does not:

- add or remove Device Catalog ICPNs;
- alter the 124 / 32 coverage baseline;
- add STM32F4 Programming Profiles;
- change OpenOCD erase/program/verify/read command templates;
- implement a Native PPU programming driver;
- change PMode / EMode IC selection behavior;
- create PPU or Socket validation evidence;
- deploy or restart services;
- access Z2, FPGA or real IC hardware.
