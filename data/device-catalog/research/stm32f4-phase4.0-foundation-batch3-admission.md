# STM32F4 Phase 4.0 Foundation Batch 3 Admission

## Scope

This phase promotes already-retained official-ST evidence for five STM32F4 base devices into the production Device Catalog. It does not change IC Support Programming Profiles, programming-algorithm equivalence, PS/PL runtime, deployment, or hardware behavior.

Admission set:

- `STM32F401CD`
- `STM32F401CE`
- `STM32F412CE`
- `STM32F412CG`
- `STM32F412ZE`

New exact admitted commercial ICPNs: **16**.

`STM32F401CC` remains the retained lifecycle control. Its Active rows were already present before this batch. `STM32F401CCF6TR` was observed as Preview and remains excluded from this batch's new admission set; the pre-existing production row is intentionally not removed by this phase.

## Evidence and mapping gate

- retained evidence: `evidence/stm32f4-phase4.0-foundation-batch3-live-2026-08-31/`
- retained evidence ID: `stm32f4-phase4.0-foundation-batch3-2026-08-31-retained-20260831T035207Z-42fa641`
- live evidence workflow run: `33355178099`
- retained live evidence artifact: `9744902128`
- live acquisition targets: `6/6` successful on the final evidence run
- exact Active candidates across control + admission targets: `20`
- new admission candidates: `16`
- all six base devices resolve uniquely through existing OpenOCD ordering patterns to `tcl/target/stm32f4x.cfg`
- only ST rows classified `Active` are new admission candidates
- the observed Preview row remains audited, not newly admitted

OpenOCD target mapping remains catalog-routing evidence only; it is not evidence that these devices share one Programming Profile or one low-level flash algorithm.

## Read-only admission proposal

Proposal workflow run: `33355504707`

Proposal artifact: `9744988636`

The isolated proposal proved:

- `candidate_count = 16`
- `admit = 16`
- `already_present = 0`
- `manual_review_required = 0`
- `reject = 0`
- `conflicts = 0`
- STM32F4 canonical rows `85 -> 101`
- isolated proposed CSV passed the existing STM32F4 canonical validator

Immutable proposal bindings:

- admission plan SHA-256: `05cbd105b923f1b363dedf59f0d2348a70e2daee88915206f929c31ba1821de0`
- proposed/final STM32F4 CSV SHA-256: `affa1b94e569a771eb7b5672fadf3ad17c8914f0d5adab27bbe23386cb88364e`
- final STM32F4 CSV Git blob: `b13f219a2496184ee4443d44164e9e449fb77529`

## Production result

- STM32F4 production exact ICPNs: `85 -> 101`
- STM32F1 production exact ICPNs: `75`
- total production exact admitted commercial ICPNs: `160 -> 176`

The production manifest is bound to the final STM32F4 CSV SHA-256 and Git blob above.

## Post-admission lifecycle proof

Offline regression requires:

1. retained evidence remains scale-ready and byte-valid;
2. current-state replanning returns `16/16 already_present` with zero new admits;
3. reconstructing the historical 85-row canonical dataset reproduces the exact pre-write admission-plan SHA-256;
4. applying that plan yields 101 rows;
5. a second application is an explicit no-op;
6. regenerated canonical bytes are identical to the checked-in 101-row production CSV;
7. the pre-existing `STM32F401CCF6TR` Preview control row remains present because this batch does not perform production lifecycle removal.

## Final CI boundary

The temporary admission-proposal and controlled-publish workflows are removed before merge. Final validation is offline/read-only and includes the normal Device Catalog production manifest/runtime checks.
