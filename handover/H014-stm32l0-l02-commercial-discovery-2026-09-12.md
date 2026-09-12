# H014 — STM32L0 L0.2 Manufacturer-Authoritative Commercial Discovery

**Date:** 2026-09-12
**Status:** Gate 1 implementation complete; PR #509 Gate 2 candidate after final-head recheck
**Primary workstream:** Device Catalog / STM32L0 commercial discovery
**Repository:** `physicslu/plasma`
**Branch:** `agent/device-catalog-stm32l0-phase-l02-discovery`
**PR:** #509

## 1. Starting state

STM32L0 L0.1 merged in PR #506 at:

`a7918156547aebbed95fe7e91d1ed2e44f389cb4`

Starting Production state:

```text
exact ICPNs:             912
Base Devices:            293
STM32 families:           10
STM32L0 Production:        0
```

L0.1 frozen surface:

```text
source rows:        166
ordering patterns:  164
CMSIS aliases:        2
subfamilies:          16
representatives:      16
```

L0.1 baseline SHA-256:

`958572fa69a4457966256851a39badfdc38490e0c3ce155978155baf3ca9e488`

## 2. Gate 1 boundary

Gate 1 approved **STM32L0 Phase L0.2 — Manufacturer-Authoritative Commercial Discovery**.

Authorized:

- collapse frozen L0.1 ordering patterns to the complete deterministic Base Device research set;
- acquire exact commercial identity and lifecycle from official ST evidence;
- retain immutable evidence, tests, hard-lock validator, CI and documentation;
- prepare PR #509 to Gate 2.

Not authorized:

- canonical admission or Production publication;
- programming-policy or Flash-algorithm equivalence claims;
- Flash geometry / option-security semantics qualification;
- socket/electrical/HIL qualification;
- runtime programming-support claims.

## 3. Deterministic research surface

The 164 frozen ordering patterns collapse to:

```text
Base Devices: 99
subfamilies:  16
L0.1 representatives retained: 16/16
```

Offline negative controls: 9/9 PASS.

## 4. Manufacturer-authoritative acquisition

Authority:

`official_st_quality_and_reliability_exact_identity_plus_sample_and_buy_marketing_status_exact_set_join`

- Quality & Reliability: exact Part Number identity.
- Sample & Buy: Marketing Status.
- Exact sets must join before lifecycle disposition is accepted.

Authoritative live run:

- workflow run: `34686132303`
- artifact: `10296507776`
- artifact SHA-256: `5732782fce1911debe7360c07ccbae5ba03fd86cc097a975bc271fe9c6b334bd`
- acquisition source PR head: `996489c8fe5e871310dd42c0d06c7b0302ca0750`
- executed PR merge ref: `4423e029cea8ac541d25c87ea8612fae2a3e68ee`
- Chromium: `151.0.7922.34`
- Playwright: `1.62.0`
- parser profile: `stm32l0_l0_2_dual_surface_v1`
- headed acquisition

Result:

```text
Base Devices attempted:                  99
verified identity targets:               99
Active-candidate Base Devices:           99
Active exact ICPNs:                     360
excluded non-Active exact PNs:           10
lifecycle-only Base Devices:              0
source unavailable:                       0
manual review:                            0
acquisition failure:                      0
OpenOCD unique routing targets:           99
routing follow-up:                        0
L0.1 representative continuity:         PASS
bounded discovery:                     CLEAN
```

The 360 Active exact ICPNs are research candidates only and are not Production.

## 5. Excluded non-Active exact Part Numbers

- `STM32L011K4T7`
- `STM32L011K4U7`
- `STM32L021F4U7TR`
- `STM32L021G4U7`
- `STM32L021K4T7`
- `STM32L031F4P7`
- `STM32L071RZT7`
- `STM32L071VBT7`
- `STM32L071VZT7`
- `STM32L073V8T7`

Set digests:

- Base Device set: `1c9dc41c8f8dc44a132e8303e0c88b2168dc3bbf745a6250aa7f382e57d5f8af`
- Active exact ICPN set: `8c7f0cc10829ff5e1ceb98cf6783247a5f685a9f1407dbd560a350348c0a521b`
- excluded non-Active set: `86be718862ed2641a3e857d0d7016aca459852d7dc3f210123893b28f66a6960`

## 6. Retained evidence

Evidence root:

`data/device-catalog/research/evidence/stm32l0-l0.2-official-st-discovery-live-2026-09-12/`

Evidence ID:

`stm32l0-l0.2-official-st-discovery-2026-09-12-retained-20260912T110725Z-996489c8`

The retained summary embeds all 99 evidence records. The original 99 leaf files are represented by an immutable leaf digest map; the permanent validator reconstructs each canonical leaf byte-for-byte and checks its digest.

Important retained SHA-256 values:

- live summary: `c664e6458d00f169b2653021284acb56664b607c245e97f51bf13f4a232d51de`
- targets: `72350a146038c09b43516715f52cddf06ee5d05f1a4ab737a994744d43e166ed`
- acquisition provenance: `2e7379f865b0f5e23101517f58d7a53ec5076820a0240369d99cb34b1f08862c`
- leaf digest map: `79b562f6eb87081544cd409c399d68f3afa06f644501a243d272be37004c4502`
- retention provenance: `23bd258b75f687b01e43beb249f759b4d71a704ba56480ce170c054017cb635f`
- retained manifest: `66e4c248398e8986878538c3dde7cc3811df0f3f1a0fbbbd2b1f46c77a20e97a`

## 7. Permanent implementation

- `data/device-catalog/research/stm32l0_phase_l0_2_discovery.py`
- `data/device-catalog/research/run_stm32l0_phase_l0_2_discovery.py`
- `data/device-catalog/research/test_stm32l0_phase_l0_2_discovery.py`
- `data/device-catalog/research/validate_stm32l0_phase_l0_2_retained_evidence.py`
- `data/device-catalog/research/stm32l0-phase-l0.2-discovery-manifest.json`
- `data/device-catalog/research/stm32l0-phase-l0.2-discovery-baseline.json`
- `data/device-catalog/research/device-catalog-stm32l0-phase-l0.2-discovery.md`
- `.github/workflows/device-catalog-stm32l0-l02-discovery-validation.yml`
- `.github/workflows/device-catalog-stm32l0-l02-live-discovery.yml` — manual-only live acquisition

Temporary acquisition/retention/repair workflows were removed before qualification.

## 8. Validation history

The first retained-evidence validator run failed because it assumed the immutable Production prestate had an `entries` array. The existing L0.1 contract exposes `sources[]` with `family` and `row_count`. The validator was corrected to use that established contract; no retained evidence bytes or commercial identity semantics changed.

Qualification head:

`f166d000c08d2d1f2f2154d0ded4a470a2e7d8d7`

passed:

- STM32L0 L0.2 discovery validation — run `34690722116` — SUCCESS
- Repository contracts — run `34690722124` — SUCCESS
- Device catalog validation — run `34690722134` — SUCCESS
- Device catalog current validation — run `34690722146` — SUCCESS

The branch was also synchronized fail-closed with `main = c0af23ef5ef763218f08ffe21642e884858539fa`; the intervening main changes had no device-catalog path overlap.

A documentation-only final head must still be rechecked before Gate 2.

## 9. Production boundary

L0.2 performs zero Production writes.

```text
Production exact ICPNs: 912 (delta 0)
Production Base Devices: 293 (delta 0)
Production families: 10 (delta 0)
STM32L0 Production: 0
```

## 10. Next action

Recheck PR #509 final head, current `main`, all CI, compare state, reviews and review threads. If merge-ready, request explicit **Gate 2 merge approval**.

Any subsequent STM32L0 metadata/policy/admission phase is a separate transaction and requires a new Gate 1 after PR #509 merges.
