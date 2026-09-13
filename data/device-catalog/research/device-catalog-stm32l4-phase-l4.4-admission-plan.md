# STM32L4 Phase L4.4 — Read-only Capability / Admission Plan

## Scope

L4.4 consumes the closed L4.3 manufacturer-authoritative metadata result and performs one additional read-only capability gate: exact-ICPN routing through the frozen OpenOCD ordering-pattern catalog.

This phase does not write canonical or Production data and does not establish physical programming support.

## Frozen input

- Base Devices: 138
- manufacturer-verified Active exact ICPNs: 446
- metadata-ready exact ICPNs: 446
- metadata-ready exact-set SHA-256: `cdb350bdf1513f51430808b98677948569740d230c45bd735f439142ab03eb45`
- metadata rows SHA-256: `d67e27b641b295df697b804741b7be1abbb2ee26dd7a24e11482640306bef500`
- L4.3 baseline Git blob: `176c043ab97285ad7c488ffa4de06c4c20e13c1e`

## Capability authority

OpenOCD is used only as a routing/capability observation.

Required route:

`tcl/target/stm32l4x.cfg`

A candidate is capability-admittable only when its exact ICPN resolves to one deterministic STM32L4 ordering pattern mapped to that target config.

OpenOCD does not redefine manufacturer identity, lifecycle status, package/pin/Flash/temperature metadata, or ordering suffix semantics.

## Exact-level replay

The canonical OpenOCD catalog is hard-bound to Git blob:

`0ef056e3363e20bb527590c4a4cc1cc0d7afb810`

Frozen replay result:

```text
manufacturer-verified exact ICPNs: 446
metadata-ready exact ICPNs:        446
unique OpenOCD routes:             446
ambiguous routes:                    0
unmapped routes:                     0
capability-admittable:             446
capability-unresolved:               0
identity rejects:                    0
```

The empty capability-unresolved set SHA-256 is:

`01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b`

## Canonical admission planning

The canonical STM32L4 dataset is absent before admission planning. L4.4 therefore plans 446 `admit` decisions and zero `already_present`, `manual_review_required`, or `reject` decisions.

This is a plan only. No canonical CSV is written by L4.4.

Frozen plan:

`data/device-catalog/research/stm32l4-phase-l4.4-admission-plan.json`

Hard-lock validator:

`data/device-catalog/research/validate_stm32l4_phase_l4_4_admission_plan.py`

## Production boundary

Production remains unchanged:

```text
Production exact ICPNs:    1272
Production Base Devices:    392
Production STM32 families:   11
STM32L4 Production:           0
```

Production prestate SHA-256:

`c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec`

## What L4.4 does not prove

A clean OpenOCD route does not prove physical programming support. L4.4 does not qualify:

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

A future L4.5 transaction may perform controlled publication of the capability-admittable exact ICPNs. L4.5 is a separate transaction and requires a new Gate 1 after L4.4 merges.
