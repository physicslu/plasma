# STM32L4 Phase L4.5 — Controlled Publication

## Scope

L4.5 publishes exactly the 446 exact ICPNs frozen as capability-admittable by L4.4.

This transaction changes Device Catalog identity availability only. It does not establish physical programming support.

## Frozen input

- Base Devices: 138
- manufacturer-verified Active exact ICPNs: 446
- metadata-ready exact ICPNs: 446
- capability-admittable exact ICPNs: 446
- capability-unresolved: 0
- L4.4 admission-plan Git blob: `ec660436dd6866abca28a63d6bac774f9ab50e49`
- admitted exact-set SHA-256: `cdb350bdf1513f51430808b98677948569740d230c45bd735f439142ab03eb45`
- OpenOCD catalog Git blob: `0ef056e3363e20bb527590c4a4cc1cc0d7afb810`

## Production prestate

```text
Production exact ICPNs: 1272
Production Base Devices: 392
STM32 families: 11
STM32L4 Production: 0
```

Frozen manifest:

- Git blob: `4e6a53695e86729063acd8ae102f66cc7eeb06c8`
- SHA-256: `c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec`

## Publication result

Canonical dataset:

`data/device-catalog/research/stm32l4-commercial-icpn.csv`

Published:

```text
exact ICPNs: 446
Base Devices: 138
```

Canonical hard lock:

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

Post-publication Production manifest:

- Git blob: `ee77f620ba77015382239c15bd6459aad60f19b0`
- SHA-256: `bea4ef5bda39e26bf0a8aef9c2bee33c5b1233452f1f4b83c944495bc9a3f2e4`

## Production poststate

```text
Production exact ICPNs: 1718  (delta +446)
Production Base Devices: 530 (delta +138)
STM32 families: 12              (delta +1)
STM32L4 Production: 446
```

The 446 published rows are catalog identities. They are not 446 physically qualified programmer targets.

## Manufacturer exception continuity

The three exact L4.3 manufacturer-authority exceptions remain explicit in canonical metadata and do not expand identity scope:

- `STM32L4A6RGT7`
- `STM32L4A6RGT7TR`
- `STM32L4S5QII3P`

## Explicit non-claims

L4.5 does not qualify:

- Flash programming algorithm equivalence;
- Flash geometry equivalence;
- erase/program/verify behavior;
- option bytes or security transitions;
- PPU/FPGA/SWD electrical behavior;
- Socket / adapter correctness;
- real-IC HIL;
- runtime programming support.

## Permanent validation

- `publish_stm32l4_phase_l4_5.py` deterministically reconstructs the publication from frozen inputs and is idempotent after publication.
- `test_stm32l4_phase_l4_5_publication.py` verifies identity set, canonical semantics, manufacturer-exception continuity, Production binding, and non-claim boundaries.
- `validate_stm32l4_phase_l4_5_publication.py` hard-locks all materialized publication bytes.
- `.github/workflows/device-catalog-stm32l4-l45-publication-validation.yml` provides permanent read-only CI.

The temporary write-capable materialization workflow removed itself after committing deterministic outputs.
