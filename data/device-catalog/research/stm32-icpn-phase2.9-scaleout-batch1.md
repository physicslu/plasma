# STM32 ICPN Phase 2.9 — Bounded Scale-out Batch 1

## Decision

Phase 2.9 begins STM32F1 scale-out only after the Phase 2.8 generic admission framework was validated. This batch is deliberately bounded to eight previously untreated STM32F1 base devices rather than sweeping the remaining family.

The selected bases are:

- `STM32F100CB`
- `STM32F100VE`
- `STM32F101RE`
- `STM32F101ZE`
- `STM32F102CB`
- `STM32F103RC`
- `STM32F105VB`
- `STM32F107RC`

All eight have one unique CMSIS/OpenOCD mapping to `tcl/target/stm32f1x.cfg`. The batch stays inside the STM32F1 policy's validated package and flash-density grammar so this phase tests bounded scale-out mechanics rather than introducing new metadata semantics.

## Research baseline

`stm32f1-phase2.9-scaleout-baseline.json` records 26 expected exact commercial ICPNs across the eight targets.

The baseline is research expectation only. It is not retained browser evidence, contains no rendered-DOM or evidence-section digests, and is not itself eligible for canonical admission.

## Live evidence result

The approved headed-Chromium sequence completed successfully on executed Git SHA `396213d9d7dc4c3cfa40278e64d922e75ae20c3d`.

- Chromium: `151.0.7922.34`
- control `STM32F100CB`: 1/1 success
- full pilot: 8/8 success
- acquisition transport: `chromium_rendered_dom` for 8/8
- exact ICPN candidates: 26
- candidate baseline exact match: true
- candidate drift: 0
- `scale_ready=true`
- live evidence retains `canonical_dataset_admission=false`

Retained evidence ID:

`stm32f1-phase2.9-scaleout-batch1-2026-08-29-retained-20260829T161336Z-396213d`

The retained package is stored under:

`evidence/stm32f1-phase2.9-scaleout-batch1-live-2026-08-29/`

The retained evidence remains manufacturer evidence only. Canonical admission is a separate deterministic decision.

## Admission result

`stm32f1-phase2.9-admission-plan.json` is retained as the immutable pre-write audit artifact. It records:

- canonical rows before admission: 49
- candidate count: 26
- `admit`: 26
- `already_present`: 0
- `manual_review_required`: 0
- `reject`: 0
- conflicts: 0
- issues: none

The canonical dataset was then advanced from 49 rows to 75 rows using exactly the row semantics captured by that admission plan.

Post-admission validation requires all 26 Phase 2.9 rows to match their checked-in `proposed_canonical_row` exactly. Rebuilding the Phase 2.9 plan from retained evidence against the current 75-row canonical dataset must classify all 26 as `already_present`, with zero admits, rejects, manual-review decisions, conflicts, or issues.

The generic admission writer contract is also tested by reconstructing the bound 49-row pre-write state from the current canonical dataset, applying the checked-in Phase 2.9 plan once, and applying the same plan a second time. The required results are:

1. first application: `status=written`, 49 → 75, 26 added;
2. second application: `status=no_op`, 75 → 75, zero added.

## Historical admission compatibility

Phase 2.7 remains an immutable historical audit artifact, not a permanent assertion that the canonical dataset must remain exactly 49 rows.

Historical validation now separates two invariants:

1. the original Phase 2.7 pre-write state can still be reconstructed and reproduces the checked-in historical plan exactly;
2. the current canonical dataset may contain later valid admissions, provided every Phase 2.7 admitted row remains byte-for-byte semantically identical and the historical planner still classifies all 26 historical candidates as `already_present`.

This prevents later bounded admissions from invalidating historical evidence while still detecting deletion, mutation, duplication, or semantic conflict in previously admitted rows.

## One-command live runbook

`run_stm32f1_phase2_9_scaleout.py` remains a read-only live-acquisition orchestrator. It performs:

1. clean-worktree and full Git-SHA binding;
2. headed-Chromium control run for `STM32F100CB`;
3. headed-Chromium eight-target pilot;
4. deterministic evaluation against the checked-in Phase 2.9 baseline;
5. evidence retention with manifest/provenance SHA-256 digests;
6. immediate offline retained-evidence validation;
7. read-only scale-out admission planning against the current canonical dataset.

It stops on the first failed stage. It does not contain a canonical writer and reports `canonical_dataset_written=false`. Canonical mutation remains a separate reviewed action.

## CI boundary

Normal GitHub CI remains offline and deterministic. It does not install Chromium/Playwright and does not contact ST.

The CI contract now validates:

- the eight-target manifest and baseline identity;
- the 26-candidate baseline shape;
- unique OpenOCD/CMSIS mapping for every selected base;
- compatibility of all 26 commercial identities with the existing STM32F1 policy;
- historical browser-control defaults plus the explicit Phase 2.9 control;
- retained live evidence integrity and provenance;
- generic admission framework behavior;
- historical Phase 2.7 reproducibility and compatibility with later canonical admissions;
- the 75-row canonical dataset with no duplicate ICPNs and complete authoritative provenance;
- exact equality between the 26 Phase 2.9 proposed rows and current canonical rows;
- post-admission Phase 2.9 re-planning as 26/26 `already_present`;
- single-apply plus second-run `no_op` writer idempotency.

GitHub Actions `Device catalog validation` run `33263108854` passed all validation steps on head `008308832ec933210374a96a1c364ad07903a457` before this documentation-only update.

## Scope boundary

This batch does not authorize a remaining-STM32F1 sweep, another manufacturer, inferred commercial identifiers, relaxed evidence requirements, a canonical schema change, deployment, service restart, runtime Web/API work, FPGA/Z2 operation, or real-IC operation.
