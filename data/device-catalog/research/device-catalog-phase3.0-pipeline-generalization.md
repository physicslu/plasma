# Device Catalog Phase 3.0 — Evidence Pipeline Generalization

## Decision

Phase 3.0 turns the STM32F1-proven evidence/admission flow into a reusable pipeline boundary without adding catalog coverage.

This is a framework-only phase:

- canonical STM32F1 dataset remains exactly 75 rows;
- no ICPN is added, removed, or edited;
- retained Phase 2.6 and Phase 2.9 evidence packages remain immutable;
- checked-in Phase 2.7 and Phase 2.9 admission plans remain historical audit artifacts;
- no live manufacturer access is performed;
- no new manufacturer/family adapter is implemented yet.

## Ownership model

```text
Manufacturer / family adapter
  - source authority
  - acquisition/transport qualification
  - exact ICPN extraction
  - deterministic reevaluation
  - metadata and programming mapping policy
                 |
                 v
Generic retained-evidence framework
  - manifest schema
  - exact retained-file membership
  - SHA-256 integrity
  - evidence identity
  - repository / full Git-SHA provenance
  - acquisition accounting
  - retained evidence can never claim canonical admission
                 |
                 v
Generic evidence-to-admission pipeline
  - normalized AdmissionInputs
  - expected candidate-count binding
  - compose adapter output with canonical state
                 |
                 v
Generic admission framework
  - deterministic ordering
  - admit/already-present/manual-review/reject
  - duplicate/conflict detection
  - canonical semantic SHA binding
  - clean-plan gate
  - idempotent writer
                 |
                 v
Canonical device catalog
```

## New generic contracts

### `device_catalog_evidence_framework.py`

Owns vendor/transport-neutral retained-evidence mechanics:

- deterministic SHA-256 manifest construction;
- exact file membership and digest validation;
- non-empty immutable `evidence_id`;
- manufacturer, repository, full Git SHA and acquisition transport provenance;
- target success/failure accounting;
- exact candidate-count provenance;
- `scale_ready=true` as the retained batch outcome;
- `canonical_dataset_admission=false` as a hard boundary.

The framework intentionally treats acquisition transport as opaque. Synthetic regression proves that `official_json` and `raw_http` transports and a non-ST manufacturer can pass the generic layer.

### `device_catalog_pipeline_framework.py`

Defines normalized `AdmissionInputs` and composes them with the existing generic admission framework.

It intentionally has no knowledge of:

- STMicroelectronics;
- STM32 family names;
- Chromium/Playwright;
- manufacturer URL grammar;
- part-number grammar;
- OpenOCD CFG naming.

The manufacturer/family adapter remains responsible for candidate and canonical-row policy.

## STM32F1 composition after Phase 3.0

`validate_stm32f1_retained_evidence.py` now delegates generic package and provenance invariants to the evidence framework, then applies only STM32F1/ST-specific rules:

- official ST URL validation;
- headed `chromium_rendered_dom` evidence;
- rendered-DOM/evidence-section digest semantics;
- exact candidate ownership by STM32F1 base device;
- baseline identity and deterministic reevaluation;
- Playwright/Chromium provenance.

`retain_stm32f1_browser_evidence.py` delegates manifest construction and SHA-256 digest mechanics to the generic evidence framework while retaining STM32F1 browser/evaluator semantics.

`stm32f1_scaleout_admission.py` is now an STM32F1 adapter over the generic pipeline framework. Historical Phase 2.9 keys remain compatibility/audit aliases; the checked-in historical plan is not rewritten.

## Regression requirements

Phase 3.0 is acceptable only if all of the following hold on one final PR head:

- canonical STM32F1 row count remains 75;
- 75/75 commercial rows retain valid mapping and authoritative provenance;
- retained Phase 2.6 evidence validates unchanged;
- retained Phase 2.9 evidence validates unchanged;
- Phase 2.9 re-plan remains 26/26 `already_present`, zero blocked decisions;
- historical Phase 2.7 admission remains valid;
- historical Phase 2.9 pre-write plan remains valid and idempotent;
- generic evidence synthetic non-ST tests pass;
- generic pipeline synthetic non-ST tests pass;
- generic admission framework tests pass;
- normal GitHub CI remains fully offline and deterministic.

## Deliberate non-goals

Phase 3.0 does **not** implement:

- a universal scraper;
- a universal part-number grammar;
- automatic discovery of manufacturer source authority;
- a universal programming-capability resolver;
- another manufacturer;
- another STM32 family;
- a canonical schema migration;
- runtime IC Selector/API integration.

Those abstractions require real evidence from Phase 3.1, where a second family is used to challenge this boundary.

## Production roadmap boundary

Phase 3.0 is framework stabilization, not another open-ended research loop.

- Phase 3.1: validate the boundary with a second real family without modifying generic core unless a demonstrated missing invariant exists.
- Phase 3.2: productize catalog consumption, update/error handling, and IC Selector/API integration. Phase 3.2 completion is the ICPN v1 Production Ready target.

## Scope boundary

No live ST access, no new ICPNs, no canonical row mutation, no deployment/service restart, no runtime Web/API change, no FPGA/Z2 operation, and no real-IC operation are authorized by Phase 3.0.
