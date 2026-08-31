# STM32F4 Phase 4.0 Foundation Batch 5 Admission

## Scope

This phase promotes retained official-ST evidence for five policy-ready STM32F4 base devices into the production Device Catalog. It does not change IC Support Programming Profiles, programming-algorithm equivalence, PS/PL runtime, deployment, or hardware behavior.

Admission set:

- `STM32F437VI`
- `STM32F437ZG`
- `STM32F437ZI`
- `STM32F439VG`
- `STM32F439VI`

New exact admitted commercial ICPNs: **10**.

`STM32F437VG` is the retained lifecycle control; its four Active exact ICPNs were already in production before this batch. `STM32F437VIT6WTR` was observed as **NRND** and is retained only as lifecycle evidence; it is not admitted.

## Evidence and mapping gate

- retained evidence: `evidence/stm32f4-phase4.0-foundation-batch5-live-2026-08-31/`
- retained evidence ID: `stm32f4-phase4.0-foundation-batch5-2026-08-31-retained-20260831T053303Z-5f76683`
- baseline-locked live evidence workflow run: `33360874862`
- retained live evidence artifact: `9746660760`
- retained artifact ZIP SHA-256: `668a96c350150ae075e9e81a6088063c1f0f076cb799d933a2106277ad31c9b9`
- live acquisition targets: `6/6` successful on the first bounded acquisition attempt
- exact Active candidates across control + admission targets: `14`
- new admission candidates: `10`
- candidate baseline drift: `0`
- all six base devices resolve uniquely through existing OpenOCD ordering patterns to `tcl/target/stm32f4x.cfg`
- only ST rows classified `Active` are admission candidates
- `STM32F437VIT6WTR` remains NRND/audit-only

The baseline-locked evidence run completed cleanly without transport retry. The bounded retry mechanism remains available only for transient browser/readiness failure; candidate or lifecycle-audit drift remains a hard failure.

OpenOCD target mapping remains catalog-routing evidence only; it is not evidence that these devices share one Programming Profile or one low-level flash algorithm.

## Read-only admission proposal

Proposal workflow run: `33361381534`

Proposal artifact: `9746791945`

The isolated proposal proved:

- `candidate_count = 10`
- `admit = 10`
- `already_present = 0`
- `manual_review_required = 0`
- `reject = 0`
- `conflicts = 0`
- STM32F4 canonical rows `114 -> 124`
- isolated proposed CSV passed the existing STM32F4 canonical validator

Immutable proposal bindings:

- admission plan SHA-256: `25fb27441e32ad38cb8fe3148d061c85d8e2b42cf684117d3db9b0ca5968ee29`
- proposed/final STM32F4 CSV SHA-256: `22f999adb9627231df7b332650271320d96f1957913481a5cb7a57155d9d1b6b`
- final STM32F4 CSV Git blob: `c0bb4971fa44eb818f423fc2a85efa1ffc06e81f`

## Production result

- STM32F4 production exact ICPNs: `114 -> 124`
- STM32F1 production exact ICPNs: `75`
- total production exact admitted commercial ICPNs: `189 -> 199`

The production manifest is bound to the final STM32F4 CSV SHA-256 and Git blob above.

## Base-drift handling

The transaction started from `main` commit `1e5c680fb4632340d0c9b0cfe117ab05cd038f81`, the merge result of Batch4. Before controlled publish, `main` was rechecked and remained at the same commit, so the Device Catalog production baseline did not drift during admission.

After publish and closure work, `main` advanced to `83ea3ad9d88fe87dc0439ae597eedb3b664075db` through PR #261 (`windows: fix packaged Console static asset serving`). The newer `main` production manifest was inspected directly and still reports STM32F4 row count `114`, CSV SHA-256 `f90a3a5dd94e1d43ae2ddc208c372bdfd7fdb99cc03c5848b34f3c242a051687`, and Git blob `2d8428e02f61ce5f7453ff0dc1667e150878d74c`. Therefore the base move is unrelated to Device Catalog state. Final exact-head PR CI is re-triggered after this observation so the synthetic merge is validated against the newer `main`; stale green runs from the older base are not accepted as the merge gate.

## Post-admission lifecycle proof

Offline regression requires:

1. retained evidence remains scale-ready and byte-valid;
2. current-state replanning returns `10/10 already_present` with zero new admits;
3. reconstructing the historical 114-row canonical dataset from pre-Batch5 evidence provenance reproduces the exact pre-write admission-plan SHA-256;
4. applying that plan yields 124 rows;
5. a second application is an explicit no-op;
6. regenerated canonical SHA-256 equals the checked-in 124-row production CSV;
7. `STM32F437VIT6WTR` remains absent from production;
8. the pre-existing `STM32F437VG` lifecycle-control ICPNs remain present.

## Runtime and REST regression

The runtime catalog metadata is updated to `199` total admitted exact ICPNs with taxonomy `STM32F1=75` and `STM32F4=124`. Search-result limits remain capped at 100; the metadata count is the source of truth for the full family size.

`STM32F437ZIT7TR` is the Batch5 representative exact runtime/REST regression. It must resolve as an admitted `STM32F4` row with LQFP package, 144 pins, 2048 KiB flash, and `tcl/target/stm32f4x.cfg` routing.

## Final CI boundary

The temporary discovery, live-evidence, retention, admission-proposal, and controlled-publish workflows are removed before merge. Final validation is offline/read-only and includes Device Catalog historical replay, production manifest/runtime checks, Python/PL regression, PPU release, Mock CD, browser runtime acceptance, and canonical terminology checks.
