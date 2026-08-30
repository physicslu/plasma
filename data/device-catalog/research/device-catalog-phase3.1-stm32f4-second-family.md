# Device Catalog Phase 3.1 — STM32F4 Second-Family Validation

## Decision

Phase 3.1 validates the Phase 3.0 generic ICPN pipeline with a second real STM32 family rather than adding another abstraction layer.

The result is positive: STM32F4 introduces materially different family policy — OpenOCD `ordering_pattern` mapping instead of STM32F1-style base-device exact mapping — but the Phase 3.0 generic evidence, pipeline, and admission cores require no modification.

Phase 3.1 therefore closes the framework-validation loop and establishes Phase 3.2 productization as the next milestone toward ICPN v1 Production Ready.

## Bounded scope

The live pilot is intentionally limited to four STM32F4 base devices selected to exercise different package, pin-count, flash-size, temperature-grade, and ordering-pattern semantics:

- `STM32F401CC`
- `STM32F407VG`
- `STM32F411CE`
- `STM32F429ZI`

The checked-in official-ST baseline contains 18 exact commercial ICPNs.

This phase is not an STM32F4 family sweep.

## Family-specific mapping difference

STM32F1 canonical admission can map commercial base identities to exact catalog identities. STM32F4 catalog coverage instead contains OpenOCD ordering patterns such as:

- `STM32F401CCF6TR` -> `STM32F401CCFx`
- `STM32F407VGT6TR` -> `STM32F407VGTx`
- `STM32F411CEY3TR` -> `STM32F411CEYx`
- `STM32F429ZIY6TR` -> `STM32F429ZIYx`

The STM32F4 adapter removes packing-only `TR` / `TT` suffixes, performs deterministic full ordering-pattern matching, and requires exactly one matching pattern and one OpenOCD target configuration.

All 18 admitted ICPNs resolve to:

` tcl/target/stm32f4x.cfg `

This behavior belongs to `stm32f4_admission_policy.py`; it is deliberately not generalized into the pipeline core.

## Live manufacturer evidence

One temporary PR-only workflow executed the bounded acquisition through real headed Chromium and was removed after evidence capture so final CI remains offline and deterministic.

Live workflow:

- workflow: `STM32F4 Phase 3.1 live evidence`
- run ID: `33288113800`
- executed Git SHA: `b42d460459911ddcb347fc470661a931fd911ce1`
- Playwright: `1.62.0`
- Chromium: `151.0.7922.34`
- transport: `chromium_rendered_dom`

Results:

- control: 1/1 PASS
- bounded pilot: 4/4 PASS
- exact ICPN candidates: 18
- candidate baseline exact match: true
- candidate drift: 0
- ordering-pattern/OpenOCD mapping: 4/4 targets, 18/18 exact candidates
- manual intervention: 0
- `scale_ready=true`
- retained evidence keeps `canonical_dataset_admission=false`

Evidence ID:

`stm32f4-phase3.1-bounded-pilot-2026-08-30-retained-20260830T023035Z-b42d460`

The retained package is checked in under:

`data/device-catalog/research/evidence/stm32f4-phase3.1-bounded-pilot-live-2026-08-30/`

Its manifest and file digests are validated offline on every device-catalog CI run.

## Pre-write admission audit

The live read-only admission plan was produced against an empty STM32F4 canonical dataset:

- canonical rows before: 0
- candidates: 18
- `admit`: 18
- `already_present`: 0
- `manual_review_required`: 0
- `reject`: 0
- conflicts: 0
- issues: none

Rather than granting the temporary live workflow repository-write permission or reserializing a large audit artifact through another transport, Phase 3.1 retains a compact immutable audit binding:

`stm32f4-phase3.1-admission-audit.json`

The audit records the live plan SHA-256 and all material input bindings. Offline CI reconstructs the complete pre-write plan from the retained evidence and original logical input identity, serializes it deterministically, and requires byte-level SHA-256 equality with the live artifact.

Live admission-plan SHA-256:

`b2bb003b238db1b6f5274f2011cc40d2f8764f21222f29837708c2ae3f4bd2fe`

This keeps the live workflow at `contents: read` and avoids expanding the security boundary solely for audit persistence.

## Canonical admission

`stm32f4-commercial-icpn.csv` now contains exactly 18 Phase 3.1 rows.

Every row is bound to the retained evidence ID and records:

- exact ICPN;
- STM32F4 family/base identity;
- package and pin count;
- flash size;
- temperature grade;
- packing suffix;
- deterministic OpenOCD ordering-pattern identifier;
- `tcl/target/stm32f4x.cfg`;
- direct official-ST retained-browser provenance.

`cmsis_device_name` remains empty because Phase 3.1 has not proven an exact CMSIS commercial-ordering identity. The catalog does not claim evidence that was not established.

The canonical validator re-resolves every exact ICPN against the current OpenOCD research catalog and rejects drift, ambiguity, source-binding changes, duplicates, or unsupported claims.

## Post-admission lifecycle proof

Offline regression proves the complete lifecycle:

1. retained evidence validates byte-for-byte through its manifest;
2. deterministic reevaluation remains `scale_ready` with zero candidate drift;
3. current canonical contains exactly the 18 baseline ICPNs;
4. current-state replanning yields 18/18 `already_present`, zero `admit`, zero blocked decisions;
5. an empty pre-write canonical reconstructs the original live 18-`admit` plan with the exact live plan SHA-256;
6. the generic writer applies the plan from 0 -> 18 rows;
7. the produced CSV is byte-identical to the checked-in canonical CSV;
8. applying the same plan a second time returns explicit `no_op`.

## Generic-core invariant

Phase 3.1 must not be considered successful if STM32F4 required family behavior to leak into the Phase 3.0 generic core.

The following generic files are unchanged by Phase 3.1:

- `device_catalog_evidence_framework.py`
- `device_catalog_pipeline_framework.py`
- `device_catalog_admission_framework.py`

The family-specific difference is contained in the STM32F4 adapter/policy layer.

This is the central architectural evidence produced by Phase 3.1.

## CI model

The one-time live Chromium workflow was removed after the evidence artifact was retained.

Normal `Device catalog validation` remains offline and deterministic. It covers:

- all historical STM32F1 regressions;
- generic evidence framework;
- generic pipeline framework;
- generic admission framework;
- STM32F4 policy and ordering-pattern mapping;
- STM32F4 synthetic pipeline lifecycle;
- retained live STM32F4 evidence integrity;
- STM32F4 canonical validation;
- current-state 18/18 already-present replanning;
- pre-write live-plan SHA reconstruction;
- generic writer 0 -> 18 and second-run no-op;
- byte-identical canonical output.

## Production roadmap

Phase 3.1 is the last framework-validation phase for ICPN v1.

The next phase is Phase 3.2 productization:

- define the runtime catalog consumption boundary;
- integrate ICPN lookup/search with IC Selector;
- expose the required read-only API/contract to PMode and EMode;
- define catalog version/update/error behavior;
- preserve provenance and programming-capability status in product-facing data;
- add production acceptance tests.

Phase 3.2 completion is the ICPN v1 Production Ready target. Additional STM32 families and additional manufacturers become catalog expansion work rather than blockers for first production use.

## Scope boundary

Phase 3.1 performs no deployment, service restart, runtime Web/API integration, FPGA/Z2 operation, or real-IC programming operation.
