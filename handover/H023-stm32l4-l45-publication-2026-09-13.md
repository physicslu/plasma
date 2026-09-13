# H023 — STM32L4 L4.5 Controlled Publication

## Transaction

- Phase: STM32L4 L4.5
- PR: #535
- Branch: `agent/device-catalog-stm32l4-phase-l45-publication`
- Gate 1: explicitly approved
- Gate 2: not yet approved
- Publication scope: exactly the 446 L4.4 capability-admittable exact ICPNs

## Starting state

L4.4 merged in PR #534 at:

`f785dd12e00a515415e0a62564f2d65b631184bf`

Frozen L4.4 result:

```text
Base Devices:                 138
manufacturer-verified ICPNs: 446
metadata-ready ICPNs:        446
capability-admittable:       446
capability-unresolved:         0
```

Frozen exact-set SHA-256:

`cdb350bdf1513f51430808b98677948569740d230c45bd735f439142ab03eb45`

Frozen L4.4 plan Git blob:

`ec660436dd6866abca28a63d6bac774f9ab50e49`

## Publication result

Canonical STM32L4 dataset:

`data/device-catalog/research/stm32l4-commercial-icpn.csv`

Published:

```text
exact ICPNs: 446
Base Devices: 138
```

Canonical hashes:

- Git blob: `5548df18cd8a8797ad8d2c3d3160af1c4c85cfad`
- SHA-256: `75062ea1ac51cfa66f0fd76025f74504aad92ea8f982f9b7b2c743ab541fe93e`

Publication proposal:

- Git blob: `0d849436a304e2363d30915cfdef54c1d6d6e3f7`
- SHA-256: `2347bf8158e3ca6441ad8a6484130f3dfed98c3592a2ac9f4539a4768a97b16e`

Publication audit:

- Git blob: `8914420c67266234e5ef671ebff1e6156f856500`
- SHA-256: `295d174fae4a02bd03c2ca3872b47e3dbc378afe3ebfc0aee07fd943fc81c7c4`

Publication baseline Git blob:

`dd031a661cf0c3734eb0dd3f6bd7d274de708c8f`

## Production transition

Prestate:

```text
Production exact ICPNs: 1272
Production Base Devices: 392
STM32 families: 11
STM32L4 Production: 0
```

Poststate:

```text
Production exact ICPNs: 1718
Production Base Devices: 530
STM32 families: 12
STM32L4 Production: 446
```

Post-publication manifest:

- Git blob: `ee77f620ba77015382239c15bd6459aad60f19b0`
- SHA-256: `bea4ef5bda39e26bf0a8aef9c2bee33c5b1233452f1f4b83c944495bc9a3f2e4`

## Boundary

Publication means catalog identity availability only. L4.5 does **not** claim:

- programming algorithm equivalence;
- Flash geometry equivalence;
- erase/program/verify qualification;
- option/security qualification;
- PPU/FPGA/SWD electrical qualification;
- socket/adapter qualification;
- real-IC HIL;
- runtime programming support.

## Permanent assets

- `data/device-catalog/research/stm32l4-commercial-icpn.csv`
- `data/device-catalog/research/publish_stm32l4_phase_l4_5.py`
- `data/device-catalog/research/test_stm32l4_phase_l4_5_publication.py`
- `data/device-catalog/research/validate_stm32l4_phase_l4_5_publication.py`
- `data/device-catalog/research/stm32l4-phase-l4.5-publication-proposal.json`
- `data/device-catalog/research/stm32l4-phase-l4.5-publication-audit.json`
- `data/device-catalog/research/stm32l4-phase-l4.5-publication-baseline.json`
- `data/device-catalog/research/device-catalog-stm32l4-phase-l4.5-publication.md`
- `.github/workflows/device-catalog-stm32l4-l45-publication-validation.yml`
- `data/device-catalog/production/icpn-v1-manifest.json`

The temporary materialization workflow removed itself after deterministic generation; permanent CI is read-only.

## Continuation

Before Gate 2:

1. ensure PR #535 final-head applicable CI is green;
2. confirm current `main`, PR mergeability, and review/comment blockers;
3. confirm Production delta is exactly +446 STM32L4 rows and no unrelated Production change exists;
4. obtain explicit Gate 2 merge approval.

After merge, do not automatically infer physical programmer support from catalog publication. Any next STM32 family selection or hardware/runtime qualification requires its own Gate 1 scope.
