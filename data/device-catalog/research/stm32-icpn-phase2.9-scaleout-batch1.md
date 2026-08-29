# STM32 ICPN Phase 2.9 — Bounded Scale-out Batch 1

## Decision

Phase 2.9 begins STM32F1 scale-out only after the Phase 2.8 generic admission framework was validated. This batch is deliberately bounded to eight untreated STM32F1 base devices rather than sweeping the remaining family.

The selected bases are:

- `STM32F100CB`
- `STM32F100VE`
- `STM32F101RE`
- `STM32F101ZE`
- `STM32F102CB`
- `STM32F103RC`
- `STM32F105VB`
- `STM32F107RC`

All eight already have one unique CMSIS/OpenOCD mapping to `tcl/target/stm32f1x.cfg`. The batch also stays inside the STM32F1 policy's currently validated C/R/V/Z package classes and B/C/E flash-density codes so that this phase tests scale-out mechanics rather than mixing in a new metadata grammar.

## Research baseline

`stm32f1-phase2.9-scaleout-baseline.json` records the expected exact commercial ICPN surface observed on the official ST product pages on 2026-08-29. It contains 26 expected exact ICPNs across the eight targets.

This baseline is **research expectation only**. It is not retained browser evidence, does not contain rendered-DOM or evidence-section digests, and must never be used directly for canonical admission.

## Required live sequence

Live execution remains outside normal GitHub CI.

1. Run headed Chromium against one explicit control target, `STM32F100CB`.
2. Stop immediately if the control target fails, redirects outside the approved ST product URL, exposes an access challenge, or cannot produce valid scoped evidence.
3. Only after the control succeeds, run the complete eight-target manifest with a fresh Chromium process per target.
4. Evaluate the resulting summary against `stm32f1-phase2.9-scaleout-baseline.json` using the existing live-pilot evaluator.
5. Require all of the following before retention:
   - 8/8 acquisition success;
   - unique canonical/base mapping for 8/8;
   - OpenOCD CFG mapping for 8/8;
   - valid `chromium_rendered_dom` provenance for 8/8;
   - 26 exact ICPNs;
   - exact baseline match;
   - zero candidate drift;
   - `scale_ready=true`;
   - `canonical_dataset_admission=false`.
6. Retain the successful evidence package with immutable digests and runtime provenance.
7. Build a read-only admission plan from the retained package.
8. Only after human/review confirmation of that plan may a separate canonical-write step occur.
9. Admission remains deterministic/offline and fails closed on duplicates, conflicts, mapping ambiguity, evidence integrity failures, or policy rejection.
10. After a future canonical write, re-run the planner and require newly admitted rows to become `already_present`; a second writer application must be `no_op`.

## One-command live runbook

`run_stm32f1_phase2_9_scaleout.py` executes the approved sequence in a clean Git worktree:

```bash
python data/device-catalog/research/run_stm32f1_phase2_9_scaleout.py \
  --evidence-dir data/device-catalog/research/evidence/stm32f1-phase2.9-scaleout-batch1-<timestamp> \
  --admission-plan /tmp/stm32f1-phase2.9-admission-plan.json
```

The command performs, in order:

1. clean-worktree and full Git-SHA binding;
2. headed-Chromium control run for `STM32F100CB`;
3. headed-Chromium eight-target pilot;
4. deterministic evaluation against the checked-in Phase 2.9 baseline;
5. evidence retention with manifest/provenance SHA-256 digests;
6. immediate offline retained-evidence validation;
7. read-only scale-out admission planning against the current canonical dataset.

It stops on the first failed stage. It does **not** contain a canonical writer and reports `canonical_dataset_written=false`.

## Browser control command contract

The browser runner keeps the historical `STM32F100C8` control as its default. Phase 2.9 adds an explicit `--control-base-device` option so a bounded manifest can nominate its own control without changing historical Phase 2.6 behavior.

For this batch, the live control is `STM32F100CB` and the full pilot uses `stm32f1-phase2.9-scaleout-manifest.json`.

## Retention and admission generalization

The retained-evidence validator no longer assumes the historical six-target / 26-candidate Phase 2.6 package. Target identity and candidate count are derived from the selected validated baseline. Compatibility with the historical Phase 2.6 package remains mandatory.

`stm32f1_scaleout_admission.py` is a read-only wrapper over the Phase 2.8 generic admission framework. It derives the expected candidate count from the retained evidence baseline rather than introducing a new batch-size constant. The historical Phase 2.7 26-candidate invariant remains isolated in the historical admission wrapper.

## CI boundary

Normal GitHub CI remains completely offline and deterministic. It validates:

- the eight-target manifest contract;
- manifest/baseline identity;
- the 26-candidate research baseline shape;
- absence of duplicates and overlap with the current 49-row canonical dataset;
- unique OpenOCD/CMSIS mapping for every selected base;
- compatibility of all 26 expected commercial identities with the existing STM32F1 admission policy;
- historical browser-control defaults plus the new explicit-control option;
- dynamic eight-target evidence retention contract;
- one-command orchestration is headed, fail-fast, Git-SHA-bound, and read-only with respect to canonical data;
- generic scale-out admission planning reuses historical retained evidence without a fixed batch-size assumption;
- all prior retained-evidence, generic admission, historical Phase 2.7, and canonical validators.

CI must not install Chromium/Playwright or contact ST.

## Scope boundary

This batch does not authorize a remaining-STM32F1 sweep, another manufacturer, inferred commercial identifiers, relaxed evidence requirements, a canonical schema change, deployment, service restart, runtime Web/API work, FPGA/Z2 operation, or real-IC operation.
