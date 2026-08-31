# STM32F4 Phase 4.0 Foundation Batch 2 Admission

## Scope

This phase promotes already-retained official-ST evidence for five STM32F4 base devices into the production Device Catalog. It does not change IC Support Programming Profiles, programming-algorithm equivalence, PS/PL runtime, deployment, or hardware behavior.

Admission set:

- `STM32F405VG`
- `STM32F405ZG`
- `STM32F415ZG`
- `STM32F417VG`
- `STM32F417ZG`

New exact admitted commercial ICPNs: **13**.

## Evidence and mapping gate

- retained evidence: `evidence/stm32f4-phase4.0-foundation-batch2-live-2026-08-31/`
- retained evidence ID: `stm32f4-phase4.0-foundation-batch2-2026-08-31-retained-20260831T013557Z-8979938`
- all 13 exact ICPNs resolve uniquely through existing OpenOCD ordering patterns to `tcl/target/stm32f4x.cfg`
- only ST rows classified `Active` are admitted
- observed NRND/Preview rows remain excluded/audited

OpenOCD target mapping remains catalog-routing evidence only; it is not evidence that these devices share one Programming Profile or one low-level flash algorithm.

## Read-only admission proposal

Proposal workflow run: `33349865580`

Proposal artifact: `9743221103`

The isolated proposal proved:

- `candidate_count = 13`
- `admit = 13`
- `already_present = 0`
- `manual_review_required = 0`
- `reject = 0`
- `conflicts = 0`
- STM32F4 canonical rows `72 -> 85`
- isolated proposed CSV passed the existing STM32F4 canonical validator

Immutable proposal bindings:

- admission plan SHA-256: `b3987cd7c07370adc2409d2a320d030b8f96865d2a47b3e386f0eae6bcee9386`
- proposed/final STM32F4 CSV SHA-256: `c0c649cee1bf2c8880783d3c36584f1cc1e589dfb256a5213f37eb37f0c3342f`
- final STM32F4 CSV Git blob: `7b7c3b62ad253c722d1baf70736fd45a0509f0a4`

## Production result

- STM32F4 production exact ICPNs: `72 -> 85`
- STM32F1 production exact ICPNs: `75`
- total production exact admitted commercial ICPNs: `147 -> 160`

The production manifest is bound to the final STM32F4 CSV SHA-256 and Git blob above.

## Post-admission lifecycle proof

Offline regression requires:

1. retained evidence remains scale-ready and byte-valid;
2. current-state replanning returns `13/13 already_present` with zero new admits;
3. reconstructing the historical 72-row canonical dataset reproduces the exact pre-write admission-plan SHA-256;
4. applying that plan yields 85 rows;
5. a second application is an explicit no-op;
6. regenerated canonical bytes are identical to the checked-in 85-row production CSV.

## Final CI boundary

The temporary admission-proposal and controlled-publish workflows are removed before merge. Final validation is offline/read-only and includes the normal Device Catalog production manifest/runtime checks.
