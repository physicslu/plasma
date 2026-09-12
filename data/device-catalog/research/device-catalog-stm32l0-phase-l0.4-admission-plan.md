# STM32L0 Phase L0.4 — Read-only Capability / Admission Plan

## Scope

L0.4 consumes the closed L0.3 manufacturer-authoritative metadata result and performs one additional read-only capability gate: exact-ICPN routing through the frozen OpenOCD ordering-pattern catalog.

This phase does not write canonical or Production data and does not establish physical programming support.

## Frozen input

- Base Devices: 99
- manufacturer-verified Active exact ICPNs: 360
- metadata-ready exact ICPNs: 360
- metadata-ready exact-set SHA-256: `8c7f0cc10829ff5e1ceb98cf6783247a5f685a9f1407dbd560a350348c0a521b`
- metadata rows SHA-256: `6aefd256256febb6d5f48ec58e44b5fec64489593df333c68723581eb7786a95`
- L0.3 baseline Git blob: `2cd2e001bc34c1f1335ae78e352e496e59d1e698`

## Capability authority

OpenOCD is used only as a routing/capability observation.

Required route:

` tcl/target/stm32l0.cfg `

A candidate is capability-admittable only when its exact ICPN resolves to one deterministic STM32L0 ordering pattern mapped to that target config.

OpenOCD does not redefine:

- manufacturer identity;
- lifecycle status;
- package / pin / Flash / temperature metadata;
- ordering suffix semantics.

## Exact-level replay

The current canonical OpenOCD catalog is hard-bound to Git blob:

`0ef056e3363e20bb527590c4a4cc1cc0d7afb810`

Replay result:

```text
manufacturer-verified exact ICPNs: 360
metadata-ready exact ICPNs:        360
unique OpenOCD routes:             360
ambiguous routes:                    0
unmapped routes:                     0
capability-admittable:             360
capability-unresolved:               0
identity rejects:                    0
```

Unlike STM32C0 C0.4, no mixed or unresolved exact-ICPN routing cases were observed for the frozen STM32L0 surface.

The empty capability-unresolved set SHA-256 is:

`01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b`

## Canonical admission planning

The canonical STM32L0 dataset is absent before admission planning. L0.4 therefore plans 360 `admit` decisions and zero `already_present`, `manual_review_required`, or `reject` decisions.

This is a plan only. No canonical CSV is written by L0.4.

Frozen plan:

`data/device-catalog/research/stm32l0-phase-l0.4-admission-plan.json`

Hard-lock validator:

`data/device-catalog/research/validate_stm32l0_phase_l0_4_admission_plan.py`

## Production boundary

Production remains unchanged:

```text
Production exact ICPNs:    912
Production Base Devices:   293
Production STM32 families: 10
STM32L0 Production:          0
```

Production manifest Git blob:

`8abfcc870e51ac4232cdf8d807828cfe4ff5662d`

## What L0.4 does not prove

A clean OpenOCD route does not prove physical programming support. L0.4 does not qualify:

- Flash-controller or Flash-geometry equivalence;
- erase / program / verify behavior;
- option bytes or security transitions;
- PPU hardware behavior;
- Socket / adapter correctness;
- FPGA / SWD electrical behavior;
- real-IC HIL;
- runtime programming support.

Those require separate physical/runtime evidence.

## Next phase

A future L0.5 transaction may perform controlled publication of the 360 capability-admittable exact ICPNs. L0.5 is a separate transaction and requires a new Gate 1 after L0.4 merges.
