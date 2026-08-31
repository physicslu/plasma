# STM32F4 Phase 4.0 Foundation Batch 2 Admission

## Scope

This phase promotes the already-retained official-ST evidence for five new STM32F4 base devices into the production Device Catalog. It does not change IC Support Programming Profiles, programming-algorithm equivalence, PS/PL runtime, deployment, or hardware behavior.

Admission set:

- STM32F405VG
- STM32F405ZG
- STM32F415ZG
- STM32F417VG
- STM32F417ZG

Expected exact ICPNs: 13.

## Preconditions

- retained evidence directory: `evidence/stm32f4-phase4.0-foundation-batch2-live-2026-08-31/`
- all 13 exact ICPNs must resolve uniquely through existing OpenOCD ordering patterns to `tcl/target/stm32f4x.cfg`
- only ST rows currently classified `Active` are eligible for new admission
- NRND/Preview rows remain excluded/audited
- current STM32F4 production rows: 72

## Admission gate

The PR-only admission proposal must prove:

- `candidate_count = 13`
- `admit = 13`
- `already_present = 0`
- `manual_review_required = 0`
- `reject = 0`
- `conflicts = 0`
- canonical rows `72 -> 85`
- isolated proposed CSV passes the existing STM32F4 canonical validator

Only after that proposal is retained and reviewed may the production CSV and manifest be updated.
