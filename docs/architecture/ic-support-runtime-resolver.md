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
  -> execution admission
  -> RoutedProgrammingHandler
  -> selected Site interface
       -> OpenOCD
       -> future Plasma Native PPU backend
```

`ResolvedICSupport` is not a support badge and is not physical validation. It is the deterministic join between one exact ICPN and the reusable Programming, Memory Geometry, Package / Hardware, Option and Security profiles owned by `data/ic-support/`.

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

The resolver fails closed on at least:

- missing profile or binding directories;
- malformed JSON;
- duplicate Profile IDs;
- profile kind / directory mismatch;
- duplicate exact-ICPN bindings;
- missing catalog identity fields in a binding;
- missing required profile kinds;
- dangling profile references;
- profile kind/reference mismatch;
- malformed Revision Overrides.

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

## 4. Phase 3.6 execution admission

`software/python/plasma_server/execution_router.py` owns the first runtime bridge from IC Support knowledge to execution.

For every real non-Mock Job, admission happens before:

```text
JobRegistry insertion
PPU execution-lease reservation
SiteWorker queue insertion
hardware/interface execution
```

Therefore an unsupported target cannot create a phantom queued Job or acquire PPU ownership.

### 4.1 Mock Site

Mock is a workflow simulator. It may execute any selected production-catalog ICPN without an IC Support binding.

The server-owned route metadata explicitly records:

```text
mode: mock_workflow
hardware_support_claimed: false
```

Mock success never creates real programming-support evidence.

### 4.2 OpenOCD Site

A real OpenOCD Site requires all of the following before queue admission:

1. exact `JobRequest.target` resolves through `ICSupportResolver`;
2. the resolved Programming Profile has an execution route registered by the server;
3. the Site's configured `target_cfg` matches the resolver-owned OpenOCD target identity after deterministic path normalization.

At the Phase 3.6 baseline, the only registered Programming Profile is:

```text
stm32f1-medium-density-flash-v0
```

and it must resolve to:

```text
target/stm32f1x.cfg
```

A mismatch such as an F103 ICPN with `target/stm32f4x.cfg` is a configuration error and fails closed before execution.

Path normalization accepts equivalent OpenOCD forms such as:

```text
tcl/target/stm32f1x.cfg
target/stm32f1x.cfg
/usr/share/openocd/scripts/target/stm32f1x.cfg
```

but does not allow a different target file.

### 4.3 Plasma Native / FPGA Site

The current FPGA interface is still a reserved PS/PL programming boundary. Even a resolvable F103 target is rejected during execution admission because no Native PPU runtime consumes the Programming Profile yet.

Therefore:

```text
Programming Profile resolved
    !=
Plasma Native runtime implemented
```

and:

```text
Native PPU runtime-ready exact ICPNs = 0
```

remains correct after Phase 3.6.

## 5. Handler ownership

`SiteManager` no longer constructs `STM32F103Handler` unconditionally for every enabled Site.

The runtime now separates:

```text
ProgrammingOperationHandler
    generic Erase / Program / Verify / Read stage dispatch

SiteExecutionRouter
    target identity / IC Support / backend admission

RoutedProgrammingHandler
    preserves SiteWorker's one-handler lifecycle while selecting
    the admitted Programming Profile handler per Job
```

`STM32F103Handler` remains only as a compatibility alias for older code/tests. It is no longer the SiteManager execution-selection authority.

This prevents the runtime from degenerating into direct part-number conditionals such as:

```text
if ICPN == A: use handler A
elif ICPN == B: use handler B
```

Programming Profile identity, not commercial ordering suffix, is the reusable execution-selection unit.

## 6. Server-owned resolution metadata

The admitted request receives server-owned `resolved_ic_support` metadata containing the selected route and profile identities.

Clients may not provide this field. A caller-supplied `resolved_ic_support` value is rejected as `INVALID_ARGUMENT` rather than trusted or overwritten silently.

This prevents a client from claiming a different Programming Profile or backend route than the server derived from checked-in IC Support data.

## 7. Remaining OpenOCD implementation boundary

Phase 3.6 does not promote the existing OpenOCD interface to complete programming readiness.

Known remaining implementation debt includes:

- `OpenOCDInterface.erase()` still contains a fixed `0x08000000 / 0x10000` erase template;
- OpenOCD Program / Verify / Read still require hardware-specific implementation;
- Memory Geometry, Option and Security profiles are resolved but are not yet translated into OpenOCD command generation;
- no physical PPU/Socket validation evidence is created by CI.

Consequently the route payload keeps `runtime_ready=false` for real OpenOCD execution knowledge even though target/profile admission is deterministic.

## 8. Scientific scale-out gate remains in force

The STM32F103C IC Support architecture still requires a valid isolated blind extraction result before bulk creation of new family Programming Profiles. Phase 3.6 does not weaken that gate.

The intended sequence remains:

1. deterministic exact ICPN identity;
2. evidence-backed reusable IC Support profiles;
3. resolver-driven execution admission;
4. backend command/driver implementation;
5. software/hardware validation;
6. PPU and Socket evidence as independent dimensions.

This prevents catalog coverage, OpenOCD target mapping and actual programming-algorithm readiness from collapsing into one misleading `supported=true` flag.

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
