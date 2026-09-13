# H022 — STM32L4 L4.4 Read-only Capability / Admission Plan

## Transaction

- Phase: STM32L4 L4.4
- Branch: `agent/device-catalog-stm32l4-phase-l44-admission-plan`
- Gate 1: explicitly approved
- Gate 2: not yet approved
- Production publication: not authorized

## Input boundary

L4.4 consumes exactly the closed L4.3 result:

- 138 Base Devices
- 446 manufacturer-verified Active exact ICPNs
- 446 metadata-ready exact ICPNs
- 0 metadata manual review
- 0 metadata reject
- L4.3 metadata-ready exact set SHA-256: `cdb350bdf1513f51430808b98677948569740d230c45bd735f439142ab03eb45`
- L4.3 metadata rows SHA-256: `d67e27b641b295df697b804741b7be1abbb2ee26dd7a24e11482640306bef500`
- L4.3 baseline Git blob: `176c043ab97285ad7c488ffa4de06c4c20e13c1e`

No new commercial discovery or metadata authority expansion occurs in L4.4.

## Capability authority

OpenOCD is used only as a bounded routing/capability observation.

- catalog Git blob: `0ef056e3363e20bb527590c4a4cc1cc0d7afb810`
- required target config: `tcl/target/stm32l4x.cfg`
- exact ICPN must resolve to one deterministic ordering pattern
- ambiguous or unmapped identities fail closed as capability-unresolved

OpenOCD does not override manufacturer identity, lifecycle, package, pin, Flash, temperature, option, or packing semantics.

## Frozen expected replay

```text
manufacturer-verified exact ICPNs: 446
metadata-ready exact ICPNs:        446
unique OpenOCD routes:             446
ambiguous routes:                    0
unmapped routes:                     0
capability-admittable:             446
capability-unresolved:               0
admit decisions:                   446
```

The CI transaction must independently replay this result. Any non-zero unresolved route is a failure; the result must not be repaired by broadening matching semantics without a revised Gate 1.

## Permanent files

- `data/device-catalog/research/stm32l4_admission_policy.py`
- `data/device-catalog/research/stm32l4_phase_l4_4_admission.py`
- `data/device-catalog/research/test_stm32l4_phase_l4_4_admission.py`
- `data/device-catalog/research/stm32l4-phase-l4.4-admission-plan.json`
- `data/device-catalog/research/validate_stm32l4_phase_l4_4_admission_plan.py`
- `data/device-catalog/research/device-catalog-stm32l4-phase-l4.4-admission-plan.md`
- `.github/workflows/device-catalog-stm32l4-l44-admission-validation.yml`

## Production boundary

Production prestate remains hard-bound:

- Production exact ICPNs: 1272
- Production Base Devices: 392
- Production STM32 families: 11
- STM32L4 Production exact ICPNs: 0
- Production prestate SHA-256: `c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec`

L4.4 performs no canonical or Production write.

## Explicitly not authorized by L4.4

- L4.5 controlled publication
- Flash-controller or Flash-geometry equivalence
- erase/program/verify qualification
- option-byte or security-transition qualification
- PPU/FPGA/SWD electrical qualification
- socket/adapter qualification
- real-IC HIL
- runtime programming support

## Continuation

Before Gate 2:

1. create/update the L4.4 PR;
2. ensure all applicable final CI is green on the final head;
3. confirm PR mergeability and no review/comment blockers;
4. confirm zero `data/device-catalog/production` diff and no canonical STM32L4 CSV write;
5. obtain explicit Gate 2 merge approval.

After merge, do **not** start L4.5 without a separate Gate 1 approval.
