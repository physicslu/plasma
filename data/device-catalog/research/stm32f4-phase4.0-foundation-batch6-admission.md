# STM32F4 Phase 4.0 Foundation Batch 6 Admission

## Scope

This phase promotes retained official-ST evidence for three policy-ready STM32F4 base devices into the production Device Catalog. It does not change IC Support Programming Profiles, programming-algorithm equivalence, PS/PL runtime, deployment, target power, or hardware behavior.

Admission set:

- `STM32F412ZG`
- `STM32F413CG`
- `STM32F413ZG`

New exact admitted commercial ICPNs: **9**.

`STM32F412CG` is the retained lifecycle control; its two Active exact ICPNs were already in production before this batch. Three official-ST rows were observed as **Proposal** and are retained only as lifecycle evidence, not admitted:

- `STM32F413CGU3`
- `STM32F413ZGJ3`
- `STM32F413ZGT3`

## Fresh coverage inventory and selection

The Batch6 target set was selected from a fresh post-Batch5 inventory, not from the prior batch's cached gap list:

- OpenOCD ordering-pattern Base Devices: `149`
- production STM32F4 Base Devices: `38`
- production STM32F4 exact ICPNs: `124`
- remaining Base Device gaps: `111`
- policy-ready gaps: `18`
- policy-blocked gaps: `93`

The F412/F413 cluster was selected because the three new Base Devices were already policy-ready under the existing admission policy. No package, flash-size, or mapping policy expansion was required.

## Discovery and evidence acquisition

Discovery workflow run: `33364494311`

Discovery artifact: `9747829175`

Discovery did **not** complete cleanly on its first browser transaction:

- attempt 1: `3/4` acquisition success; `STM32F413ZG` hit an ST rendered-DOM readiness timeout;
- attempt 2: whole bounded batch retried with a fresh browser and completed `4/4` clean.

The resulting candidate surface was frozen as the Batch6 baseline before the retained live-evidence transaction.

Baseline-locked live evidence workflow run: `33364791038`

Retained live evidence artifact: `9747959504`

Retained artifact ZIP SHA-256:
`8a9ce361f14e0d8a76e7f4192014d177d98b2a4685c214efc910d29fa6def5a1`

Retained evidence ID:
`stm32f4-phase4.0-foundation-batch6-2026-08-31-retained-20260831T063818Z-c3edb20`

The formal live-evidence transaction also required the bounded whole-batch retry:

- attempt 1: `2/4` acquisition success; `STM32F412CG` and `STM32F413CG` hit rendered-DOM readiness timeouts;
- attempt 2: whole bounded batch retried with a fresh browser and completed `4/4` clean.

This is acquisition flakiness and is preserved in provenance. It is not treated as evidence that ST browser acquisition is stable. The transaction remains admissible because the bounded retry policy was not exceeded and the final clean transaction reproduced the frozen candidate and non-Active lifecycle surfaces exactly.

Evidence result:

- live targets: `4/4` clean after bounded retry;
- Active exact candidates across control + admission targets: `11`;
- new admission candidates: `9`;
- Proposal/audit-only observations: `3`;
- candidate baseline drift: `0`;
- evaluator: `scale_ready=true`;
- all four Base Devices resolve uniquely through existing OpenOCD ordering patterns to `tcl/target/stm32f4x.cfg`.

Raw artifact bytes were retained through one-shot retention workflow run `33365098509`. The transaction verified the exact artifact ZIP hash, performed offline retained-evidence validation, wrote exactly six retained evidence files into the repository, and removed its own temporary workflow.

OpenOCD target mapping remains catalog-routing evidence only; it is not proof that these devices share one Programming Profile or one low-level flash algorithm.

## Read-only admission proposal

Proposal workflow run: `33365292387`

Proposal artifact: `9748055114`

Proposal artifact ZIP SHA-256:
`45bc6e0a40637eee511db61e357b3706fdb4d20d967c9871ebf8fbdc3e3f5aa1`

The isolated proposal proved:

- `candidate_count = 9`
- `admit = 9`
- `already_present = 0`
- `manual_review_required = 0`
- `reject = 0`
- `conflicts = 0`
- `issues = []`
- STM32F4 canonical rows `124 -> 133`
- isolated proposed CSV passed the existing STM32F4 canonical validator.

Immutable proposal bindings:

- admission plan SHA-256: `37591f9e8375329ab06169ccddf567259939ea2cc38ed4f6aca79044e6bdbc27`
- proposed/final STM32F4 CSV SHA-256: `4a6bf6ffbf384ce3d9c91d318b6793c710d621d6f9e11f0a6c5b50206a5acb2a`
- final STM32F4 CSV Git blob: `434443479cd8a7d5b87b723a9fde93806c4faddd`

## Controlled publish and recovery record

The first controlled-publish run, `33365419968`, correctly passed all immutable proposal, repository-local rebuild, and production precondition checks. It then failed while serializing the admission audit because the workflow incorrectly assumed the admission plan contained a `decisions` field and raised `KeyError: 'decisions'`.

No repository commit occurred in that failed run. Therefore the branch production dataset remained at the pre-Batch6 `124`-row state. The failure is recorded as a transaction implementation defect, not as evidence or catalog drift.

The corrected controlled-publish run, `33365619302`, changed only the audit serialization source for the admitted ICPN list: it reads the `added` list from the already hash-bound proposal report. The entire transaction was rerun from the beginning and again verified:

1. exact proposal artifact ZIP hash;
2. exact admission-plan SHA-256;
3. exact proposed CSV SHA-256;
4. repository-local reconstruction from retained evidence;
5. byte-for-byte equality between reconstructed and proposal plan/CSV;
6. production precondition `124` rows / pre-Batch6 CSV SHA / pre-Batch6 Git blob;
7. canonical validation after promotion;
8. one-shot workflow self-removal and controlled commit.

The corrected run completed successfully.

## Production result

- STM32F4 production exact ICPNs: `124 -> 133`
- STM32F1 production exact ICPNs: `75`
- total production exact admitted commercial ICPNs: `199 -> 208`
- final STM32F4 CSV SHA-256: `4a6bf6ffbf384ce3d9c91d318b6793c710d621d6f9e11f0a6c5b50206a5acb2a`
- final STM32F4 CSV Git blob: `434443479cd8a7d5b87b723a9fde93806c4faddd`

The production manifest is bound to the final STM32F4 CSV SHA-256 and Git blob above.

## Base-state handling

Batch6 started from merged Batch5 `main` commit `f96e62794a8aa1160c795d572bf83b763c7bcb07`. Immediately before controlled publish, `main` was rechecked and still pointed to that commit. The production manifest also still reported the exact pre-Batch6 F4 state: `124` rows, SHA-256 `22f999adb9627231df7b332650271320d96f1957913481a5cb7a57155d9d1b6b`, Git blob `c0bb4971fa44eb818f423fc2a85efa1ffc06e81f`.

The final merge gate must recheck `main` again. If `main` moves but Device Catalog state remains byte-identical, final exact-head CI must be regenerated against the newer synthetic merge. If Device Catalog state changes, the admission baseline must be reconciled rather than merged blindly.

## Post-admission lifecycle proof

Offline regression requires:

1. retained evidence remains scale-ready and byte-valid;
2. current-state replanning returns `9/9 already_present` with zero new admits;
3. reconstructing the historical 124-row canonical dataset from pre-Batch6 evidence provenance reproduces the exact pre-write admission-plan SHA-256;
4. applying that plan yields 133 rows;
5. a second application is an explicit no-op;
6. regenerated canonical SHA-256 equals the checked-in 133-row production CSV;
7. all three Proposal-only ICPNs remain absent from production;
8. the pre-existing `STM32F412CG` lifecycle-control ICPNs remain present;
9. the failed first publish run is recorded as no repository write before the corrected transaction.

## Runtime and REST regression

Runtime catalog metadata is updated to `208` total admitted exact ICPNs with taxonomy `STM32F1=75` and `STM32F4=133`. Search-result limits remain capped at 100; metadata count remains the source of truth for the full family size.

`STM32F413ZGJ6TR` is the Batch6 representative exact runtime/REST regression. It must resolve as an admitted `STM32F4` row with UFBGA package, 144 pins, 1024 KiB flash, and `tcl/target/stm32f4x.cfg` routing.

## Final CI boundary

Temporary discovery, live-evidence, retention, admission-proposal, and controlled-publish workflows are removed before merge. Final validation is offline/read-only and includes the Batch6 historical replay, production manifest/runtime checks, Python/PL regression, PPU release, Mock CD, browser runtime acceptance, and canonical terminology checks.
