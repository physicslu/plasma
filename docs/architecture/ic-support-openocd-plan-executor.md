# IC Support OpenOCD Compiled-Plan Executor

Status: **Current software-only compiled-plan executor contract; introduced in Phase 3.8**

## 1. Purpose

Plasma validates the software boundary between a canonical `OpenOCDExecutionPlan` and an external OpenOCD-like process without enabling production hardware execution.

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

## 2. Current system boundary: PS only

The current IC Support execution path stops at the programmer's **PS software layer**. The compiled-plan executor is PS/OpenOCD work.

The intended near-term physical path is:

```text
Plasma PS runtime
  -> OpenOCD compiled-plan executor
  -> OpenOCD process
  -> debug/programming adapter
  -> target IC
```

The FPGA PL is **not** part of this OpenOCD path. No current executor acceptance criterion depends on PL logic, PL registers, a PL programming engine, or PS-to-PL command transport.

A future Plasma-native PPU path may later be:

```text
ResolvedICSupport
  -> Native PPU backend
  -> PS driver
  -> PL programming engine
  -> target IC
```

but that is a separate future phase and must not be inferred from OpenOCD readiness.

## 3. Core invariant

```text
software executor validated
    !=
hardware runtime enabled
    !=
physical programming validated
    !=
PL-native programming implemented
```

`SiteExecutionRouter` therefore continues to report the production OpenOCD route as:

```text
backend_implementation_state: plan_compiled_not_executable
hardware_runtime_ready: false
```

A real Site Job still fails before JobRegistry insertion, PPU lease reservation, SiteWorker queueing or interface execution.

## 4. No default process launcher

`OpenOCDPlanExecutor` intentionally has no default process launcher.

Constructing the executor in normal runtime code is insufficient to start a process. Calling `execute()` without an explicitly injected launcher fails closed as `INTERFACE_NOT_CONFIGURED` and reports `hardware_runtime_ready=false`.

CI explicitly injects `asyncio.create_subprocess_exec`, but redirects the executable to a fake OpenOCD Python process. The current software acceptance does not configure, invoke or probe a physical adapter or IC.

## 5. Canonical-plan verification

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

## 6. Isolated artifact staging

The executor creates a fresh temporary workspace for each process execution.

Input Programming Image artifacts are:

- derived from inline `JobRequest.image` bytes only;
- checked against the plan's exact byte count;
- checked against the plan's SHA-256;
- written under an executor-generated filename, never a caller-supplied path;
- permission-restricted on POSIX hosts;
- substituted into the canonical command only after staging.

READ outputs are also assigned executor-generated paths. After the fake process exits successfully, every expected output must exist and have the exact size declared by the plan before it is returned as a named read section.

The temporary workspace is removed on success, process failure, timeout and task cancellation. Timeout and cancellation both terminate a still-running child process before returning control.

## 7. Command/process boundary

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

## 8. Fake-process CI acceptance

The regression executes a real subprocess, but the process is a fake OpenOCD Python program. It validates:

- argv construction;
- interface/target configuration placement;
- command placement as separate `-c` argv values;
- SHA-256-bound Programming Image staging;
- READ output collection;
- stdout/stderr capture;
- non-zero exit propagation;
- timeout kill behavior;
- task-cancellation kill behavior;
- missing output detection;
- wrong-size output detection;
- workspace cleanup;
- tampered-plan rejection before launch;
- invalid timeout rejection before launch;
- no-launcher fail-closed behavior.

This test proves the PS software process boundary. It does not prove that OpenOCD accepts every command against STM32F103 silicon and does not validate any PL path.

## 9. Direct OpenOCD interface remains non-executable

`OpenOCDInterface` does not own an alternate production subprocess path around the compiled-plan executor boundary.

Direct:

```text
erase
program
verify
read
```

remain fail-closed for production hardware use while the hardware runtime is disabled. `safe_shutdown()` does not create a latent OpenOCD subprocess ingress when no Job is admitted.

## 10. Current coverage meaning

The executable catalog/evidence baseline is:

```text
Exact ICPNs:                               286
Base Devices:                               91
Deterministic OpenOCD-mapped exact ICPNs:  286
Direct IC Support-bound exact ICPNs:         2
Unresolved Programming Profile ICPNs:      284
Evidence-backed Programming Profiles:        1
OpenOCD plan-compiled Programming Profiles:  1
OpenOCD plan-compiled exact ICPNs:            2
Software-executor-validated profiles:         1
Software-executor-validated exact ICPNs:      2
OpenOCD hardware-runtime-ready exact ICPNs:   0
Native PPU runtime-ready exact ICPNs:         0
```

The software-executor count must not be presented as physical programming support. Likewise, the 286 deterministic OpenOCD target mappings are catalog-routing evidence, not 286 executable Programming Profiles. Native PPU readiness remains a separate future PL-related metric and is not advanced by this executor.

## 11. Next hardware gate

A later separately approved hardware phase may evaluate whether this **PS/OpenOCD** executor can be promoted to real OpenOCD runtime use. That phase must independently validate at least:

- installed OpenOCD version and scripts on the PS-side runtime host;
- adapter/interface configuration;
- target detection;
- reset/halt behavior;
- erase/program/verify/read behavior on known STM32F103 hardware;
- cleanup/reset behavior after success, failure, timeout and cancellation;
- evidence retention for the physical test.

No PL involvement is required for that OpenOCD hardware gate.

Until that gate passes, `hardware_runtime_ready` remains false.

## 12. Non-goals

The current software executor contract does not:

- infer Programming Profiles for the 284 unresolved production exact ICPNs;
- make production OpenOCD Jobs hardware-executable;
- run a real OpenOCD binary against hardware;
- access a debug adapter, Z2, FPGA or IC;
- implement or validate PS-to-PL programming transport;
- implement the Plasma Native PPU driver or PL programming engine;
- create PPU or Socket validation evidence;
- deploy or restart Plasma services.
