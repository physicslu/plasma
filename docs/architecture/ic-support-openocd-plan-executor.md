# IC Support OpenOCD Compiled-Plan Executor

Status: **Phase 3.8 current contract**

## 1. Purpose

Phase 3.8 validates the software boundary between a canonical `OpenOCDExecutionPlan` and an external OpenOCD-like process without enabling real hardware execution.

The chain is:

```text
Exact ICPN
  -> ResolvedICSupport
  -> Programming Profile + Memory Geometry
  -> OpenOCDPlanCompiler
  -> canonical OpenOCDExecutionPlan
  -> OpenOCDPlanExecutor
  -> explicitly injected software-validation process launcher
  -> fake OpenOCD process in CI
```

The production hardware gate remains closed.

## 2. Core invariant

```text
software executor validated
    !=
hardware runtime enabled
    !=
physical programming validated
```

`SiteExecutionRouter` therefore continues to report the production OpenOCD route as:

```text
backend_implementation_state: plan_compiled_not_executable
hardware_runtime_ready: false
```

A real Site Job still fails before JobRegistry insertion, PPU lease reservation, SiteWorker queueing or interface execution.

## 3. No default process launcher

`OpenOCDPlanExecutor` intentionally has no default process launcher.

Constructing the executor in normal runtime code is insufficient to start a process. Calling `execute()` without an explicitly injected launcher fails closed as `INTERFACE_NOT_CONFIGURED` and reports `hardware_runtime_ready=false`.

CI explicitly injects `asyncio.create_subprocess_exec`, but redirects the executable to a fake OpenOCD Python process. Phase 3.8 does not configure, invoke or probe a physical adapter or IC.

## 4. Canonical-plan verification

Before any software-validation process can launch, the executor recompiles the canonical plan from:

```text
ResolvedICSupport
+ JobRequest
+ configured target_cfg
```

and requires exact equality with the supplied structured plan.

This protects at least:

- exact ICPN identity;
- operation identity;
- Programming Profile identity;
- Memory Geometry identity;
- OpenOCD target identity;
- Main Flash base and size;
- erase/program granularity;
- operation command list;
- artifact roles, sizes and hashes.

A modified or stale plan is rejected before process launch.

## 5. Isolated artifact staging

The executor creates a fresh temporary workspace for each process execution.

Input Programming Image artifacts are:

- derived from inline `JobRequest.image` bytes only;
- checked against the plan's exact byte count;
- checked against the plan's SHA-256;
- written under an executor-generated filename, never a caller-supplied path;
- permission-restricted on POSIX hosts;
- substituted into the canonical command only after staging.

READ outputs are also assigned executor-generated paths. After the fake process exits successfully, every expected output must exist and have the exact size declared by the plan before it is returned as a named read section.

The temporary workspace is removed on success, process failure and timeout.

## 6. Command/process boundary

The executor uses argv-based process launch; no shell is involved.

The process argument shape remains:

```text
<executable>
-f <interface_cfg>
-f <target_cfg>
[-c "adapter serial ..."]
-c <compiled command 1>
-c <compiled command 2>
...
```

Plan artifact tokens such as `${PLASMA_IMAGE_BIN}` are replaced only with executor-owned staging paths. Unknown or unresolved Plasma artifact tokens fail closed.

`adapter_serial` is constrained to a conservative character set before it can enter an OpenOCD command string.

## 7. Fake-process CI acceptance

The Phase 3.8 regression executes a real subprocess, but the process is a fake OpenOCD Python program. It validates:

- argv construction;
- interface/target configuration placement;
- command placement as separate `-c` argv values;
- SHA-256-bound Programming Image staging;
- READ output collection;
- stdout/stderr capture;
- non-zero exit propagation;
- timeout kill behavior;
- missing output detection;
- wrong-size output detection;
- workspace cleanup;
- tampered-plan rejection before launch;
- no-launcher fail-closed behavior.

This test proves the software process boundary. It does not prove that OpenOCD accepts every command against STM32F103 silicon.

## 8. Direct OpenOCD interface remains non-executable

`OpenOCDInterface` no longer owns an internal subprocess primitive in Phase 3.8.

Direct:

```text
erase
program
verify
read
```

remain fail-closed. `safe_shutdown()` is also a no-op while the hardware runtime is disabled, removing the previous latent subprocess path that could invoke OpenOCD even when no Job was admitted.

Therefore the only Phase 3.8 process ingress is the explicitly injected software-validation `OpenOCDPlanExecutor`.

## 9. Coverage meaning after Phase 3.8

The catalog and evidence baseline remains unchanged:

```text
Exact ICPNs:                               124
Base Devices:                               32
Evidence-backed Programming Profiles:        1
OpenOCD plan-compiled Programming Profiles:   1
OpenOCD plan-compiled exact ICPNs:            2
Software-executor-validated profiles:         1
Software-executor-validated exact ICPNs:      2
OpenOCD hardware-runtime-ready exact ICPNs:   0
Native PPU runtime-ready exact ICPNs:         0
```

The software-executor count must not be presented as physical programming support.

## 10. Next gate

A later separately approved hardware phase may evaluate whether this executor can be promoted to real OpenOCD runtime use. That phase must independently validate at least:

- installed OpenOCD version and scripts;
- adapter/interface configuration;
- target detection;
- reset/halt behavior;
- erase/program/verify/read behavior on known STM32F103 hardware;
- cleanup/reset behavior after success, failure, timeout and cancellation;
- evidence retention for the physical test.

Until that gate passes, `hardware_runtime_ready` remains false.

## 11. Non-goals

Phase 3.8 does not:

- mutate Device Catalog coverage;
- add STM32F4 Programming Profiles;
- make production OpenOCD Jobs executable;
- run a real OpenOCD binary against hardware;
- access a debug adapter, Z2, FPGA or IC;
- implement the Plasma Native PPU driver;
- create PPU or Socket validation evidence;
- deploy or restart Plasma services.
