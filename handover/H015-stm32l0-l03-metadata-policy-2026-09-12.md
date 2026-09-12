# H015 — STM32L0 L0.3 Manufacturer-Authoritative Metadata Policy

**Date:** 2026-09-12
**Status:** Gate 1 implementation complete; PR #513 Gate 2 candidate after final-head recheck
**Primary workstream:** Device Catalog / STM32L0 metadata policy
**Repository:** `physicslu/plasma`
**Branch:** `agent/device-catalog-stm32l0-phase-l03-metadata-policy`
**PR:** #513

## 1. Starting state

STM32L0 L0.2 merged in PR #509 at:

`e45d482eb5cc6360f418cce43f8634ea8545b6f5`

The independent IC Selector status UI change merged later in PR #512 at:

`6e20d47c68c43de96db22a46fd96ef91420e29e9`

L0.3 branch was synchronized non-force with that current `main` before qualification.

Starting Production state:

```text
exact ICPNs:          912
Base Devices:         293
STM32 families:        10
STM32L0 Production:     0
```

Retained L0.2 commercial boundary:

```text
Base Devices:                 99
Active exact ICPNs:          360
excluded non-Active PNs:      10
identity manual review:        0
```

## 2. Gate 1 boundary

Gate 1 approved **STM32L0 L0.3 — Metadata / Policy Qualification & Canonical Admission Readiness**.

Authorized:

- consume the frozen L0.2 360-ICPN exact identity set;
- bind package / pin / Flash / temperature / ordering suffix metadata to official ST Ordering Information;
- preserve L0-specific ordering semantics;
- deterministically classify metadata-ready / manual-review / reject;
- add tests, frozen baseline, hard-lock validator, CI, documentation and handover;
- prepare PR #513 for Gate 2.

Not authorized:

- Production publication;
- canonical admission write;
- programming algorithm / Flash-controller equivalence claims;
- option/security programming qualification;
- PPU / Socket / electrical / HIL qualification;
- runtime programming-support claims.

## 3. Official metadata authority

Metadata authority is official ST datasheet Ordering Information only. OpenOCD and CMSIS do not gate commercial metadata.

Frozen authority:

```text
STM32L0 series/subfamilies: 16
Official datasheet bindings: 19
```

Important semantics:

- STM32L010 uses four official Ordering Information documents across its six retained Base Devices and does not inherit general D/BOR suffix semantics.
- STM32L031 `S` is retained as the official UFQFPN28 one-power-pair option.
- STM32L041 `S` is also retained where applicable.

The first deterministic planner pass intentionally left 10 exact ICPNs from five L010 Base Devices in manual review because the initial retained authority bound only `STM32L010C6`. Official ST Ordering Information for F4/K4, K8/R8 and RB was then added; no metadata was guessed.

## 4. Final deterministic result

```text
Base Devices:            99
candidate exact ICPNs:   360
metadata-ready:          360
manual review:             0
reject:                    0
```

Frozen digests:

- metadata-ready exact set: `8c7f0cc10829ff5e1ceb98cf6783247a5f685a9f1407dbd560a350348c0a521b`
- metadata rows: `6aefd256256febb6d5f48ec58e44b5fec64489593df333c68723581eb7786a95`
- empty manual-review set: `01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b`
- empty reject set: `01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b`

The metadata-ready exact set is exactly the L0.2 Active exact set. L0.3 does not expand commercial identity scope.

## 5. Permanent assets

- `data/device-catalog/research/stm32l0-phase-l0.3-ordering-authority.json`
- `data/device-catalog/research/stm32l0_metadata_policy.py`
- `data/device-catalog/research/stm32l0_phase_l0_3_policy.py`
- `data/device-catalog/research/test_stm32l0_phase_l0_3_policy.py`
- `data/device-catalog/research/stm32l0-phase-l0.3-policy-baseline.json`
- `data/device-catalog/research/validate_stm32l0_phase_l0_3_policy.py`
- `data/device-catalog/research/device-catalog-stm32l0-phase-l0.3-metadata-policy.md`
- `.github/workflows/device-catalog-stm32l0-l03-metadata-validation.yml`

## 6. Validation

Dedicated L0.3 validation includes:

- 9 metadata-policy tests;
- L0.2 retained-evidence replay;
- 16-series / 19-datasheet Ordering Information binding validation;
- 360/360 metadata-ready deterministic planner replay;
- frozen exact-set and metadata-row hashes;
- immutable Production snapshot;
- fail-closed governance assertions.

The first baseline-validator run failed only because the validator compared `covered_base_devices` for L081/L082 even though that baseline field is intentionally retained only for the document-partitioned L010 authority. The comparison was corrected; baseline, authority bytes and 360 metadata rows were not changed.

Dedicated hard-lock run:

- STM32L0 L0.3 metadata validation — run `34693595288` — SUCCESS

Final-head repository-wide CI must still be rechecked after documentation-only commits.

## 7. Production boundary

L0.3 performs zero Production writes:

```text
Production exact ICPNs: 912 (delta 0)
Production Base Devices: 293 (delta 0)
Production families: 10 (delta 0)
STM32L0 Production: 0
```

No PPU/Socket/HIL/runtime programming support is established by this phase.

## 8. Next action

Recheck PR #513 final head, current `main`, CI, compare state, reviews and review threads. If merge-ready, request explicit **Gate 2 merge approval**.

After L0.3 merges, any L0.4 canonical admission/capability transaction requires a new Gate 1.
