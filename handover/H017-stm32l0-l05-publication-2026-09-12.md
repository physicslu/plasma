# H017 — STM32L0 L0.5 Controlled Publication

**Date:** 2026-09-12  
**Status:** Gate 1 implementation complete; PR #516 Gate 2 candidate after final-head recheck  
**Primary workstream:** Device Catalog / STM32L0 controlled publication  
**Repository:** `physicslu/plasma`  
**Branch:** `agent/device-catalog-stm32l0-phase-l05-publication`  
**PR:** #516

## 1. Starting state

STM32L0 L0.4 merged in PR #515 at:

`19d818037e2661aa18266c92a29a7296e98e1f00`

Frozen L0.4 result:

```text
Base Devices:                 99
manufacturer-verified ICPNs: 360
metadata-ready ICPNs:        360
capability-admittable:       360
capability-unresolved:         0
```

Frozen exact-set SHA-256:

`8c7f0cc10829ff5e1ceb98cf6783247a5f685a9f1407dbd560a350348c0a521b`

Frozen L0.4 plan Git blob:

`d46b7491ca34fa9d5c8b3adfb16709e9698e417e`

## 2. Gate 1 boundary

Gate 1 approved **STM32L0 L0.5 — Controlled Publication**.

Authorized:

- deterministically materialize the 360 L0.4-admitted exact ICPNs into canonical CSV;
- publish that exact set into the Production manifest;
- retain immutable prestate, proposal, audit and publication baseline;
- enforce idempotency and hash/cardinality hard-locks;
- repair historical L0.3/L0.4 validators so they replay frozen pre-publication state after publication;
- advance current cross-family prioritization to reflect STM32L0 now being in Production;
- add permanent read-only CI, report and handover;
- prepare PR #516 for Gate 2.

Not authorized / not claimed:

- Flash programming-algorithm equivalence;
- Flash geometry equivalence;
- option/security programming qualification;
- PPU physical validation;
- Socket physical validation;
- electrical/HIL qualification;
- runtime programming support.

## 3. Frozen Production prestate

Retained file:

`data/device-catalog/research/stm32l0-phase-l0.4-production-manifest-prestate.json`

Hashes:

- Git blob: `8abfcc870e51ac4232cdf8d807828cfe4ff5662d`
- SHA-256: `15f9c9a9be8640bc0664b562c667f676d0084e4c157e01f582c87a10886c5420`

Prestate:

```text
Production exact ICPNs: 912
Production Base Devices: 293
STM32 families: 10
STM32L0 Production: 0
```

## 4. Publication result

Canonical file:

`data/device-catalog/research/stm32l0-commercial-icpn.csv`

Published:

```text
exact ICPNs: 360
Base Devices: 99
```

Canonical hashes:

- Git blob: `8484a3ca22ae141621247e1a947b993803710467`
- SHA-256: `2a40e482b0e9084feb930b94fd2cac7029d8ecbdf4b69743f99d1e5a3c2439b7`

Publication proposal:

- Git blob: `f225f3a5c457024aa16bff7ac700db3570f41be7`
- SHA-256: `061e60ec3678d41edb182f0274ff64d935af3b026b50e4a144b2527e45652bb0`

Publication audit:

- Git blob: `03de66dd75f0d2b881fe45a4284e46a33bebfa00`
- SHA-256: `62be237f9f012e12fcb5605f8831d2954ec02907cdbb43671333b8e3f9cc44e6`

Publication baseline Git blob:

`61d49d3517c7351bec38973c116dfd1c925807e4`

Post-publication manifest:

- Git blob: `4e6a53695e86729063acd8ae102f66cc7eeb06c8`
- SHA-256: `c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec`

## 5. Production poststate

```text
Production exact ICPNs: 1272 (delta +360)
Production Base Devices: 392 (delta +99)
STM32 families: 11 (delta +1)
STM32L0 Production: 360
```

These 360 rows represent catalog identity availability. They are **not** 360 physically qualified programmer targets.

## 6. Historical-validator transition

The publication initially exposed three expected stale-current-state assumptions:

1. L0.3 metadata validation still bound current Production to 912 rows;
2. L0.4 admission validation still bound current Production and absent canonical state;
3. cross-family prioritization still expected STM32L0 to be outside Production.

Corrections:

- L0.3 now replays the immutable 912-row pre-publication Production snapshot;
- L0.4 now replays the same frozen Production snapshot plus explicit zero-row historical canonical prestate;
- L0.4 frozen summary semantics remain unchanged;
- current cross-family prioritization now excludes STM32L0 and leaves `STM32L1`, `STM32L4` as the remaining standard shortlist.

After correction, L0.3, L0.4, L0.5 and cross-family validation all pass together.

## 7. Permanent assets

- `data/device-catalog/research/stm32l0-commercial-icpn.csv`
- `data/device-catalog/research/stm32l0-phase-l0.4-production-manifest-prestate.json`
- `data/device-catalog/research/publish_stm32l0_phase_l0_5.py`
- `data/device-catalog/research/test_stm32l0_phase_l0_5_publication.py`
- `data/device-catalog/research/validate_stm32l0_phase_l0_5_publication.py`
- `data/device-catalog/research/stm32l0-phase-l0.5-publication-proposal.json`
- `data/device-catalog/research/stm32l0-phase-l0.5-publication-audit.json`
- `data/device-catalog/research/stm32l0-phase-l0.5-publication-baseline.json`
- `data/device-catalog/research/device-catalog-stm32l0-phase-l0.5-publication.md`
- `.github/workflows/device-catalog-stm32l0-l05-publication-validation.yml`

The final L0.5 workflow is read-only. The temporary bootstrap write capability was removed after deterministic materialization.

## 8. Validation state before final Gate 2 recheck

Validated after publication and historical-contract repair:

- STM32L0 L0.3 metadata validation — SUCCESS
- STM32L0 L0.4 admission validation — SUCCESS
- STM32L0 L0.5 publication validation — SUCCESS
- STM32 cross-family prioritization validation — SUCCESS
- Device catalog current validation — SUCCESS
- Device catalog validation — SUCCESS
- C0 publication/admission regressions — SUCCESS
- evidence-accessibility / post-U0 selection regressions — SUCCESS

A final-head CI and current-main drift/review check is still required before Gate 2.

## 9. Next action

Recheck PR #516 final head, current `main`, all CI, compare state, reviews and review threads. If merge-ready, request explicit **Gate 2 merge approval**.

After L0.5 merges, STM32L0 catalog publication is complete. Any physical-programming qualification or a new STM32 family transaction requires a new Gate 1.
