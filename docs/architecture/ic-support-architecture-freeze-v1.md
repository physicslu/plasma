# IC Support Architecture Freeze v1

Status: **Current frozen architecture baseline**  
Date: **2026-09-11**  
Freeze baseline commit: `7119a2878bc7d7c9b1e67822cdfc04b99368077c`

## 1. Purpose

This document freezes the first vendor-neutral IC Support architecture baseline after completion of the governance, NXP compatibility, STM32 migration, and compiler/admission-registry transactions.

The freeze is intentionally narrow. It freezes the software trust and plan-compilation architecture that exists today. It does **not** declare real-target programming, HIL, PL-native programming, Production routing expansion, destructive/security operations, or eight-Site physical qualification complete.

The baseline is the result of:

| Transaction | PR | Merge commit | Frozen result |
|---|---:|---|---|
| PR-A — Generic vendor-neutral admission governance | #474 | `39cbe4b6bbb11687ff7117dfac0b06cb856428fc` | Generic trust/admission ABI v1 |
| PR-B — NXP KL25 compatibility projection | #481 | `14b0e290c74424b057d6f50dc58f126eb6a5d8c4` | Existing immutable KL25 lineage represented in v1 |
| PR-C — STM32F103C migration | #483 | `1f68f89e80cf7fb8afc53f39b3c7fb7af8490398` | C8/CB execution-relevant semantics represented in v1 |
| PR-D — Compiler/admission registry separation | #486 | `7119a2878bc7d7c9b1e67822cdfc04b99368077c` | Admission authority separated from compiler availability |

## 2. Frozen system boundary

The software milestone stops at a controlled software execution boundary:

```text
Manufacturer Evidence
  -> Semantic Extraction / Review
  -> Post-review Disposition
  -> Candidate Review
  -> Vendor Canonical Payload
  -> Canonical Admission Envelope
  -> Operation Admission
  -> Backend Binding
  -> Compiler Registry
  -> Vendor/backend-specific Plan Compiler
  -> OpenOCDExecutionPlan
  -> Software Executor validation
  -> STOP
```

The current architecture does not allow the existence of a compiler or execution plan to imply hardware readiness.

The following inequalities are frozen invariants:

```text
reviewed
!= canonical admitted
!= operation admitted
!= production routed
!= hardware runtime ready
```

And:

```text
Specification correctness
!= Software correctness
!= Hardware correctness
!= Production readiness
```

## 3. Frozen authority model

IC Support authority remains ordered as:

```text
Manufacturer Evidence
> Validated Canonical Specification
> Generated / Compiled Implementation
> AI opinion
```

AI may assist semantic extraction and review. AI is not an authority for:

- commercial identity;
- exact target applicability;
- manufacturer truth;
- canonical admission;
- operation admission;
- destructive/security admission;
- production routing;
- hardware readiness.

The generic layer answers **why an artifact is trusted, admitted, bound, and selectable**. The vendor layer answers **how the silicon behaves**.

This architecture therefore forbids a generic cross-vendor Flash-controller semantic abstraction that pretends different vendor controllers share one unlock/erase/program state machine.

## 4. Generic vendor-neutral Admission v1

The generic governance layer owns:

- content-addressed artifact identity;
- schema identity and version;
- manufacturer-evidence references;
- exact review-subject coverage;
- post-review disposition lineage;
- candidate-review coverage;
- canonical-admission lineage;
- per-operation admission;
- backend implementation binding;
- compiler identity binding;
- structural canonical requirement resolution.

The v1 schema identities are:

- `plasma://ic-support/admission/artifact-ref-v1`
- `plasma://ic-support/admission/manufacturer-evidence-ref-v1`
- `plasma://ic-support/admission/review-binding-v1`
- `plasma://ic-support/admission/post-review-disposition-v1`
- `plasma://ic-support/admission/candidate-review-v1`
- `plasma://ic-support/admission/canonical-admission-envelope-v1`
- `plasma://ic-support/admission/operation-admission-v1`
- `plasma://ic-support/admission/backend-implementation-binding-v1`

The generic validator validates identity, digest, lineage, set coverage, structural references, state transitions, and binding consistency. It does **not** interpret target registers, command encodings, memory-controller behavior, erase semantics, security state, or other vendor-specific meaning.

### 4.1 Exact review coverage

A review binding identifies an exact content-addressed subject set. Disposition must cover exactly the same set. Missing, extra, duplicate, stale, or swapped subjects fail closed.

### 4.2 Canonical requirement binding

An admitted operation requirement binds:

- the exact vendor canonical payload artifact; and
- an absolute JSON Pointer within that payload.

Generic validation proves the artifact and path exist. Semantic correctness remains the responsibility of vendor evidence/review.

### 4.3 Operation admission

Admission is operation-specific. An admitted row binds at least:

```text
request operation
operation contract identity + digest
canonical admission digest
backend identity + backend lock digest
compiler identity
canonical requirements
admission state
hardware_runtime_ready
```

A high-level operation name alone never defines destructive scope across vendors.

## 5. NXP KL25 frozen compatibility state

Exact target:

```text
MKL25Z128VLK4
```

The NXP adapter is a deterministic compatibility projection of the retained legacy lineage. It does not rewrite historical Gate 5.7A, Gate 5.8, or #472 artifacts.

Frozen historical properties include:

- Gate 5.8 final status remains `REJECTED_REVIEW`;
- reviewed facts: 140;
- inherited all-pass facts: 130;
- findings: 10;
- transformed reviewed candidates: 13;
- projected candidates: 143;
- immutable #472 release digest: `dc256318618f20d3d5bffbee8fe74fd0c9554b7b457d448f1bc13ed86f18f987`;
- legacy NXP/OpenOCD backend lock digest: `877b3fd9c0b9f8dc3191eb53393e5670efb93b9952ac1747bded155ebcaef4d1`.

PR-B sidecar release:

- release ID: `20260911T010604Z-dc256318618f`;
- release digest: `875f8bfd71a7a02e3a62daf28b74a7f701a6202f34b14d08f5e7d87ba34aa1c8`.

Admitted Software Executor operations:

- `READ`
- `VERIFY`
- `PROGRAM`
- request-level `ERASE`, bound specifically to the NXP exact-sector `ERASE_SECTOR` contract

NXP ERASE semantics are frozen as:

- exactly one aligned 1 KiB sector;
- no implicit erase;
- the sector containing the Flash Configuration Field is prohibited.

Blocked NXP operations remain blocked, including mass erase, security modification, unprotect, backdoor-key flows, and Flash Configuration Field programming/destructive paths.

Every admitted NXP operation remains `hardware_runtime_ready=false`.

## 6. STM32F103C frozen migration state

Exact targets:

```text
STM32F103C8T6
STM32F103CBT6
```

Manufacturer authority is bounded to:

- ST `DS5319 Rev 20`
- ST `PM0075 Rev 2`

Existing identity/profile lineage is reused. The migration does not rediscover ICPNs, rerun an AI model, or rewrite historical v0-v9 research artifacts.

Shared Programming Profile:

```text
stm32f1-medium-density-flash-v0
```

Target geometry remains distinct:

| Exact ICPN | Main Flash | Page size | Memory Geometry Profile |
|---|---:|---:|---|
| `STM32F103C8T6` | 64 KiB | 1 KiB | `stm32f103c8-64k-v0` |
| `STM32F103CBT6` | 128 KiB | 1 KiB | `stm32f103cb-128k-v0` |

Admitted Software Executor operations:

- `READ`
- `VERIFY`
- `PROGRAM`
- `ERASE`

STM32 request-level `ERASE` is frozen as the existing compiler behavior:

```text
flash erase_address <resolved_main_flash_start> <resolved_main_flash_size>
```

Therefore the admitted STM32 ERASE scope is **the full resolved Main Flash range** for the exact target.

This is not represented as one-page erase and is not claimed to be semantically identical to the STM32 controller `MER` command.

Blocked STM32 operations include:

- controller Mass Erase as a separately admitted operation;
- option programming;
- option erase;
- RDP enable/disable transitions;
- write-protection changes.

Every admitted STM32 operation remains `hardware_runtime_ready=false`.

## 7. Compiler Registry freeze

Compiler availability is no longer operation authority.

The frozen selection chain is:

```text
Generic-valid admission package
  -> content-addressed runtime admission projection
  -> projection digest validation
  -> CompilerRegistry
       -> exact target + request operation admission lookup
       -> compiler_id lookup
       -> backend_id match
       -> backend_lock_digest match
  -> vendor/backend-specific compiler
  -> OpenOCDExecutionPlan
```

The runtime projection is a compiled derivative of generic-valid governance artifacts. Runtime does not import benchmark/migration modules as an authority.

The current software-only integration rejects a runtime projection when:

- its canonical digest is invalid;
- its shape/schema/governance marker is invalid;
- it contains duplicate target/operation admissions;
- an operation is not `ADMITTED`;
- `hardware_runtime_ready` is not exactly `false`;
- the selected compiler is unregistered;
- compiler/backend identity does not match the admitted backend lock.

The following distinction is frozen:

```text
compiler registered
!= operation admitted
!= target production routed
!= hardware runtime ready
```

## 8. Backend/plan compilation freeze

The compiler layer remains vendor/backend-specific.

For STM32F103C, the existing `OpenOCDPlanCompiler` derives target-specific ranges from the resolved Memory Geometry Profile.

For KL25, `KL25OpenOCDPlanCompiler` retains KL25-specific alignment, Flash Configuration Field, erase-sector, and OpenOCD target constraints.

A generated `OpenOCDExecutionPlan` is software command intent. It is not proof that OpenOCD successfully programmed a physical IC.

Production hardware execution remains fail-closed.

## 9. Explicit non-claims at Freeze v1

Architecture Freeze v1 does **not** establish any of the following:

- real MCU HIL qualification;
- physical SWD programming qualification;
- PYNQ-Z2 native target-programming qualification;
- PPU hardware runtime enablement for these admitted operations;
- FPGA/PL-native programming engine correctness;
- production target-set expansion caused by Admission v1;
- destructive/security operation admission;
- power/reset isolation qualification;
- fault containment across Sites;
- retry/recovery qualification on real ICs;
- eight-Site physical concurrency qualification;
- throughput qualification;
- manufacturing traceability closure;
- long-duration reliability qualification.

Passing Cloud, CI, fake-process, QEMU, packaging, or software-executor tests must never be reported as real-target programming evidence.

## 10. Change-control rule after Freeze v1

This freeze is an architecture baseline, not a prohibition on future change.

However, future work must not silently redefine v1 semantics.

The following require an explicit architecture change rather than incidental implementation drift:

- changing the meaning of generic Admission v1 fields;
- weakening exact review/candidate coverage;
- allowing generic validation to infer vendor silicon semantics;
- allowing compiler registration to imply admission;
- changing an admitted operation's destructive scope without a new operation-contract identity/digest and corresponding evidence/review;
- setting `hardware_runtime_ready=true` without a separately evidenced hardware-readiness transition;
- enabling destructive/security workflows merely because a backend/compiler can express them;
- treating Production routing as equivalent to admission.

An incompatible governance change should use a new versioned contract rather than mutating v1 history in place.

## 11. Source-of-truth relationship

This freeze document summarizes the architecture at the named baseline commit. It does not override executable code, checked-in schemas, tests, or newer intentional architecture decisions.

Within the freeze baseline, the main supporting contracts are:

- `docs/architecture/vendor-neutral-ic-admission.md`
- `docs/architecture/ic-support-openocd-plan-compiler.md`
- `docs/architecture/ic-support-openocd-plan-executor.md`
- `software/python/plasma_interfaces/compiler_registry.py`
- `data/ic-support/benchmarks/nxp-kl25/VENDOR_NEUTRAL_ADMISSION_ADAPTER.md`
- `data/ic-support/benchmarks/stm32f103c/VENDOR_NEUTRAL_ADMISSION_MIGRATION.md`

## 12. Recommended next phase

The next phase should not add more trust-layer abstraction merely for completeness. The software trust chain is now sufficiently separated to expose the next risk honestly: **hardware evidence**.

A separately approved hardware/runtime phase should define the evidence required to move selected operations from:

```text
operation admitted
hardware_runtime_ready = false
```

to an evidence-backed hardware-ready state.

That phase must keep target semantics, electrical behavior, adapter behavior, reset/power sequencing, cancellation/recovery, Site isolation, and retained evidence explicit. It must not infer readiness from plan compilation alone.
