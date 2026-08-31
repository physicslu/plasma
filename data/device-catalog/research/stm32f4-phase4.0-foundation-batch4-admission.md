# STM32F4 Phase 4.0 Foundation Batch 4 Admission

## Scope

This phase promotes retained official-ST evidence for five policy-ready STM32F4 base devices into the production Device Catalog. It does not change IC Support Programming Profiles, programming-algorithm equivalence, PS/PL runtime, deployment, or hardware behavior.

Admission set:

- `STM32F427VI`
- `STM32F427ZI`
- `STM32F429VE`
- `STM32F429VG`
- `STM32F429VI`

New exact admitted commercial ICPNs: **13**.

`STM32F429ZG` is the retained lifecycle control; its three Active exact ICPNs were already in production before this batch. `STM32F427VIT7` was observed as **Proposal** and is retained only as lifecycle evidence; it is not admitted.

## Evidence and mapping gate

- retained evidence: `evidence/stm32f4-phase4.0-foundation-batch4-live-2026-08-31/`
- retained evidence ID: `stm32f4-phase4.0-foundation-batch4-2026-08-31-retained-20260831T044040Z-226ad4d`
- baseline-locked live evidence workflow run: `33357781639`
- retained live evidence artifact: `9745725060`
- retained artifact ZIP SHA-256: `3347362d28342929d4ac7e39d67739ee9511d492cf7d98fec646b45cdfef56ff`
- live acquisition targets: `6/6` successful after the bounded whole-batch retry
- exact Active candidates across control + admission targets: `16`
- new admission candidates: `13`
- candidate baseline drift: `0`
- all six base devices resolve uniquely through existing OpenOCD ordering patterns to `tcl/target/stm32f4x.cfg`
- only ST rows classified `Active` are admission candidates
- `STM32F427VIT7` remains Proposal/audit-only

The first baseline-locked acquisition attempt had readiness timeouts for `STM32F427ZI` and `STM32F429VI`; a fresh-browser whole-batch retry produced a clean 6/6 acquisition with the same baseline candidate surface. The retry policy handles transport/readiness failure only; candidate drift remains a hard failure.

OpenOCD target mapping remains catalog-routing evidence only; it is not evidence that these devices share one Programming Profile or one low-level flash algorithm.

## Read-only admission proposal

Proposal workflow run: `33358153417`

Proposal artifact: `9745794283`

The isolated proposal proved:

- `candidate_count = 13`
- `admit = 13`
- `already_present = 0`
- `manual_review_required = 0`
- `reject = 0`
- `conflicts = 0`
- STM32F4 canonical rows `101 -> 114`
- isolated proposed CSV passed the existing STM32F4 canonical validator

Immutable proposal bindings:

- admission plan SHA-256: `3b705e296c0d6770360f51ceef1f147171a4ac147cc43877bfe5fd2f52dab84f`
- proposed/final STM32F4 CSV SHA-256: `f90a3a5dd94e1d43ae2ddc208c372bdfd7fdb99cc03c5848b34f3c242a051687`
- final STM32F4 CSV Git blob: `2d8428e02f61ce5f7453ff0dc1667e150878d74c`

## Production result

- STM32F4 production exact ICPNs: `101 -> 114`
- STM32F1 production exact ICPNs: `75`
- total production exact admitted commercial ICPNs: `176 -> 189`

The production manifest is bound to the final STM32F4 CSV SHA-256 and Git blob above.

## Base-drift handling

During admission, `main` advanced from Batch4's start commit `8107cd98cee68d01b888a6871ad2b97f3641c1c5` to `86760eed34784baad5c502178157b2dc450183ff` through the Windows self-contained runtime PR. The STM32F4 production manifest on the newer main remained exactly at 101 rows with the same pre-Batch4 CSV SHA-256 and Git blob, so the Device Catalog transaction baseline did not drift.

## Post-admission lifecycle proof

Offline regression requires:

1. retained evidence remains scale-ready and byte-valid;
2. current-state replanning returns `13/13 already_present` with zero new admits;
3. reconstructing the historical 101-row canonical dataset from pre-Batch4 evidence provenance reproduces the exact pre-write admission-plan SHA-256;
4. applying that plan yields 114 rows;
5. a second application is an explicit no-op;
6. regenerated canonical SHA-256 equals the checked-in 114-row production CSV;
7. `STM32F427VIT7` remains absent from production;
8. the pre-existing `STM32F429ZG` lifecycle-control ICPNs remain present.

## Final CI boundary

The temporary discovery, live-evidence, retention, admission-proposal, and controlled-publish workflows are removed before merge. Final validation is offline/read-only and includes Device Catalog historical replay, production manifest/runtime checks, Python/PL regression, PPU release, Mock CD, browser runtime acceptance, and canonical terminology checks.
