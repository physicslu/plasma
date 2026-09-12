# H016 — STM32L0 L0.4 Read-only Capability / Admission Plan

**Date:** 2026-09-12  
**Status:** Complete; PR #515 merged  
**Primary workstream:** Device Catalog / STM32L0 admission planning  
**Repository:** `physicslu/plasma`  
**Branch:** `agent/device-catalog-stm32l0-phase-l04-admission-plan`  
**PR:** #515  
**Merge commit:** `19d818037e2661aa18266c92a29a7296e98e1f00`

## 1. Starting state

STM32L0 L0.3 merged in PR #513 at:

`a7b7917aff09394f5cb550655218bcf1e22e0078`

Starting Production state:

```text
exact ICPNs:          912
Base Devices:         293
STM32 families:        10
STM32L0 Production:     0
```

Frozen L0.3 metadata boundary:

```text
Base Devices:           99
metadata-ready ICPNs:   360
manual review:            0
reject:                   0
```

L0.3 exact-set SHA-256:

`8c7f0cc10829ff5e1ceb98cf6783247a5f685a9f1407dbd560a350348c0a521b`

L0.3 metadata rows SHA-256:

`6aefd256256febb6d5f48ec58e44b5fec64489593df333c68723581eb7786a95`

## 2. Gate 1 boundary

Gate 1 approved **STM32L0 L0.4 — Read-only Capability / Admission Planning**.

Authorized:

- consume exactly the frozen L0.3 360 metadata-ready exact ICPNs;
- replay exact-ICPN OpenOCD ordering-pattern routing;
- classify capability-admittable versus capability-unresolved;
- build deterministic canonical-admission rows for the admittable subset;
- add tests, frozen plan, hard-lock validator, CI, report and handover;
- prepare PR #515 for Gate 2.

Not authorized:

- canonical dataset writes;
- Production publication;
- Flash-controller / Flash-geometry equivalence claims;
- option/security programming qualification;
- PPU / Socket / electrical / HIL qualification;
- runtime programming-support claims.

## 3. Capability gate

Required OpenOCD target config:

`tcl/target/stm32l0.cfg`

OpenOCD is only a capability-routing gate. It does not redefine manufacturer identity, lifecycle, or L0.3 metadata.

Frozen OpenOCD catalog Git blob:

`0ef056e3363e20bb527590c4a4cc1cc0d7afb810`

## 4. Deterministic exact-level result

```text
manufacturer-verified exact ICPNs: 360
metadata-ready exact ICPNs:        360
unique routes:                     360
ambiguous routes:                    0
unmapped routes:                     0
capability-admittable:             360
capability-unresolved:               0
```

Empty unresolved-set SHA-256:

`01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b`

## 5. Canonical admission plan

Canonical STM32L0 prestate was absent / zero-row.

Frozen decisions:

```text
admit:                   360
already_present:           0
manual_review_required:    0
reject:                    0
```

L0.4 remained read-only: the canonical dataset was not written.

Frozen plan Git blob:

`d46b7491ca34fa9d5c8b3adfb16709e9698e417e`

## 6. Final Gate 2 transaction

Before merge, `main` advanced through unrelated PR #514. The L0.4 branch was therefore non-force merge-forwarded with the new `main`, then final CI was rerun.

Final pre-merge state:

- branch head: `59eddfc29120c0c433e28c60d52c02da506725b7`
- `main`: `034350ad7ba72fa176a158cb043ba3f9ea5dbdd7`
- STM32L0 L0.4 admission validation — SUCCESS
- Device catalog validation — SUCCESS
- Device catalog current validation — SUCCESS
- Repository contracts — SUCCESS
- reviews: 0
- review threads: 0

Gate 2 was explicitly approved and PR #515 merged at:

`19d818037e2661aa18266c92a29a7296e98e1f00`

## 7. Permanent assets

- `data/device-catalog/research/stm32l0_admission_policy.py`
- `data/device-catalog/research/stm32l0_phase_l0_4_admission.py`
- `data/device-catalog/research/test_stm32l0_phase_l0_4_admission.py`
- `data/device-catalog/research/stm32l0-phase-l0.4-admission-plan.json`
- `data/device-catalog/research/validate_stm32l0_phase_l0_4_admission_plan.py`
- `data/device-catalog/research/device-catalog-stm32l0-phase-l0.4-admission-plan.md`
- `.github/workflows/device-catalog-stm32l0-l04-admission-validation.yml`

## 8. Production boundary at L0.4 completion

```text
Production exact ICPNs: 912 (delta 0)
Production Base Devices: 293 (delta 0)
Production families: 10 (delta 0)
STM32L0 Production: 0
```

A capability-admittable result does not establish physical programming support.

## 9. Continuation

L0.4 is historical and complete. Use **H017** for STM32L0 L0.5 controlled publication and later state.
