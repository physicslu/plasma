# H008 — IC Support Architecture Freeze v1 Handover

**Date:** 2026-09-11  
**Status:** Current engineering handover / Architecture Freeze v1  
**Primary workstream:** AI IC Support / Vendor-Neutral Admission  
**Repository:** `physicslu/plasma`  
**Freeze baseline `main`:** `7119a2878bc7d7c9b1e67822cdfc04b99368077c`

---

## 1. Executive Summary

The vendor-neutral IC Support architecture sequence defined by H007 is complete through PR-D.

```text
PR-A Generic trust ABI                  DONE
PR-B NXP real-vendor compatibility      DONE
PR-C STM32F103C migration               DONE
PR-D Compiler/admission registry        DONE
Architecture Freeze v1                  CURRENT TRANSACTION
```

Architecture Freeze v1 does not add programming capability. It records the architecture that is now proven at software/governance level and freezes the distinctions that future hardware/runtime work must preserve.

The normative freeze document is:

```text
docs/architecture/ic-support-architecture-freeze-v1.md
```

The central architecture is now:

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

Do not collapse the following states:

```text
reviewed
!= canonical admitted
!= operation admitted
!= production routed
!= hardware runtime ready
```

And do not collapse:

```text
Specification correctness
!= Software correctness
!= Hardware correctness
!= Production readiness
```

---

## 2. Completed Transaction Ledger

### PR-A — Generic vendor-neutral admission governance

- PR: `#474`
- Merge commit: `39cbe4b6bbb11687ff7117dfac0b06cb856428fc`
- Result: content-addressed generic Admission v1 trust/governance ABI
- Generic validator owns structure, identity, lineage, digest, exact coverage, and structural binding
- Generic validator does not interpret vendor silicon semantics

### PR-B — NXP KL25 compatibility adapter

- PR: `#481`
- Final head: `669d5222525ec06ec000ef319f9ceffffaebbc76`
- Merge commit: `14b0e290c74424b057d6f50dc58f126eb6a5d8c4`
- Sidecar release ID: `20260911T010604Z-dc256318618f`
- Sidecar release digest: `875f8bfd71a7a02e3a62daf28b74a7f701a6202f34b14d08f5e7d87ba34aa1c8`

Frozen NXP historical facts:

- exact target `MKL25Z128VLK4`
- Gate 5.8 remains permanently `REJECTED_REVIEW`
- retained facts: 140
- inherited full-PASS facts: 130
- findings: 10
- transformed reviewed candidates: 13
- projected candidates: 143
- immutable #472 release digest: `dc256318618f20d3d5bffbee8fe74fd0c9554b7b457d448f1bc13ed86f18f987`
- legacy backend lock digest: `877b3fd9c0b9f8dc3191eb53393e5670efb93b9952ac1747bded155ebcaef4d1`

Admitted NXP software operations:

- READ
- VERIFY
- PROGRAM
- request-level ERASE bound only to exact-sector `ERASE_SECTOR`

NXP ERASE contract:

- exactly one aligned 1 KiB sector
- no implicit erase
- sector containing the Flash Configuration Field is prohibited

Destructive/security workflows remain blocked and `hardware_runtime_ready=false`.

### PR-C — STM32F103C vendor-neutral migration

- PR: `#483`
- Final head: `8fb45ccb269f861302a1992bdfe0a204dc1bd2d7`
- Merge commit: `1f68f89e80cf7fb8afc53f39b3c7fb7af8490398`

Exact targets:

- `STM32F103C8T6`
- `STM32F103CBT6`

Manufacturer authority:

- ST `DS5319 Rev 20`
- ST `PM0075 Rev 2`

Existing exact ICPN identity and profile lineage were reused. No ICPN rediscovery, model rerun, historical v0-v9 rewrite, or compiler behavior change was performed.

Shared Programming Profile:

`stm32f1-medium-density-flash-v0`

Geometry:

| Target | Main Flash | Page size | Geometry Profile |
|---|---:|---:|---|
| `STM32F103C8T6` | 64 KiB | 1 KiB | `stm32f103c8-64k-v0` |
| `STM32F103CBT6` | 128 KiB | 1 KiB | `stm32f103cb-128k-v0` |

Admitted STM32 software operations:

- READ
- VERIFY
- PROGRAM
- ERASE

STM32 ERASE contract is the current application/compiler behavior:

```text
flash erase_address <resolved_main_flash_start> <resolved_main_flash_size>
```

Therefore STM32 ERASE means **full resolved Main Flash range erase**. It is not a one-page erase contract and is not claimed to be semantically identical to controller `MER`.

Controller Mass Erase as an operation, option operations, RDP transitions, and write-protection changes remain blocked. `hardware_runtime_ready=false`.

### PR-D — Compiler/admission registry separation

- PR: `#486`
- Final head: `663f33319877ff8e2cb090c5de7d4963a1b9db16`
- Merge commit / Freeze baseline: `7119a2878bc7d7c9b1e67822cdfc04b99368077c`

PR-D removed compiler availability as operation authority.

Frozen runtime selection path:

```text
generic-valid admission package
  -> checked content-addressed runtime projection
  -> CompilerRegistry
  -> exact target + request operation admission
  -> compiler_id
  -> backend_id + backend_lock_digest match
  -> vendor/backend compiler
  -> OpenOCDExecutionPlan
```

The runtime projection fails closed on digest/shape errors, duplicate target-operation rows, non-admitted rows, or `hardware_runtime_ready=true`.

Final latest-main merge-ref validation before PR-D merge:

- all 10 pull-request workflows PASS
- Python/PL full test result: `797 passed, 98 subtests passed`

---

## 3. Historical H007 Relationship

H007 was created before PR-B was visible on GitHub. Its statements about PR-B being unverified were correct at the time and must remain historical rather than being rewritten.

H008 supersedes H007 for **current continuation state**.

Use H007 for:

- original architecture reasoning;
- NXP retained evidence/review history;
- original frozen PR-B/PR-C/PR-D intent.

Use H008 plus current repository code/tests for:

- present completion state;
- Architecture Freeze v1 baseline;
- next-step planning.

---

## 4. Frozen Trust Model

Authority order remains:

```text
Manufacturer Evidence
> Validated Canonical Specification
> Generated / Compiled Implementation
> AI opinion
```

Generic governance and vendor semantics remain different layers:

```text
Generic layer = why an artifact is trusted/admitted/bound/selectable
Vendor layer  = how the silicon actually works
```

Do not create a generic cross-vendor Flash state machine that hides STM32/NXP controller differences.

A common request operation name is not a common destructive scope.

The NXP vs STM32 ERASE difference is the canonical example:

```text
NXP ERASE    -> one exact aligned 1 KiB sector
STM32 ERASE  -> full resolved Main Flash range
```

Both are allowed only because each request operation is bound to its own target-owned operation contract identity/digest.

---

## 5. Compiler Registry Boundary

`CompilerRegistry` is a selector, not an admission authority.

The registry requires:

- exact target + operation admission row;
- admission state `ADMITTED`;
- registered `compiler_id`;
- exact `backend_id` match;
- exact `backend_lock_digest` match.

The default runtime projection is content-addressed and is generated/checked against generic-valid admission lineage in CI. Runtime does not import benchmark/migration code as authority.

Current software-only runtime integration rejects a projection with `hardware_runtime_ready=true`.

Therefore:

```text
compiler registered
!= operation admitted
!= production routed
!= hardware ready
```

---

## 6. Explicitly Unproven / Closed Boundaries

Architecture Freeze v1 does not prove or enable:

- real MCU HIL;
- physical SWD programming;
- Z2 native target-programming readiness;
- PPU hardware runtime enablement for admitted operations;
- FPGA/PL-native programming engine;
- Production routing expansion due to Admission v1;
- destructive/security programming operations;
- power/reset isolation qualification;
- Site fault containment;
- real-target retry/recovery;
- eight-Site physical concurrency;
- throughput qualification;
- manufacturing traceability closure;
- long-duration reliability.

A passing CI, fake-process executor, QEMU, package build, or plan compiler is software evidence only.

---

## 7. Change-Control Rule After Freeze v1

Future implementation may extend the system, but it must not silently redefine v1.

The following require an explicit architecture decision/versioned change:

- weaken exact review/candidate coverage;
- change Generic Admission v1 field meaning;
- make generic validation infer silicon semantics;
- make compiler registration imply operation admission;
- change destructive scope without a new operation contract and evidence/review;
- set `hardware_runtime_ready=true` without hardware evidence;
- enable destructive/security flows merely because the compiler/backend can express them;
- treat Production routing as equivalent to admission.

For incompatible governance changes, create a new version instead of rewriting v1 history.

---

## 8. Repository References

Normative/current architecture:

- `docs/architecture/ic-support-architecture-freeze-v1.md`
- `docs/architecture/vendor-neutral-ic-admission.md`
- `docs/architecture/ic-support-openocd-plan-compiler.md`
- `docs/architecture/ic-support-openocd-plan-executor.md`
- `software/python/plasma_interfaces/compiler_registry.py`

Vendor-specific compatibility/migration records:

- `data/ic-support/benchmarks/nxp-kl25/VENDOR_NEUTRAL_ADMISSION_ADAPTER.md`
- `data/ic-support/benchmarks/stm32f103c/VENDOR_NEUTRAL_ADMISSION_MIGRATION.md`

Historical handover:

- `handover/H007-vendor-neutral-ic-admission-handover-2026-09-10.md`

---

## 9. Recommended Continuation

The next material risk is not another generic abstraction layer. It is the evidence required to cross the hardware boundary.

A future Gate 1 should define a bounded hardware/runtime qualification transaction that answers:

```text
What exact evidence is required to move one target/operation from

operation admitted
hardware_runtime_ready = false

into an evidence-backed hardware-ready state?
```

That work should define, before enabling hardware:

- exact target and adapter;
- physical interface and voltage/power/reset boundary;
- OpenOCD/runtime/backend revision;
- operation-specific erase/program/verify/read expectations;
- final reset/state expectations;
- cancellation/recovery behavior;
- retained evidence format;
- Site isolation/fault-containment requirements;
- explicit destructive-operation exclusions.

Do not start by enabling all admitted operations or all targets.

A single exact target with a narrow non-security operation set is the correct first hardware qualification unit.

---

## 10. Copy/Paste Prompt for the Next Session

```text
Read repo handover H008 and the IC Support Architecture Freeze v1 document.

Treat PR-A #474, PR-B #481, PR-C #483, and PR-D #486 as closed architecture transactions. Preserve the frozen distinction between generic governance, vendor semantics, operation admission, compiler availability, Production routing, and hardware readiness.

Do not reopen ICPN discovery, rerun AI semantics, expand Production routing, enable destructive/security operations, or set hardware_runtime_ready=true as incidental work.

If continuing toward hardware, first perform a bounded Gate 1 design for one exact target and a narrow operation set, with explicit HIL/electrical/runtime evidence requirements. Do not infer hardware readiness from CI, plan compilation, fake-process execution, or QEMU evidence.
```

---

**End of H008.**
