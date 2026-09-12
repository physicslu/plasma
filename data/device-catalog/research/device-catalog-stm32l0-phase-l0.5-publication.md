# Device Catalog — STM32L0 Phase L0.5 Controlled Publication

## Status and scope

Phase L0.5 is the controlled canonical + Production publication transaction for the exact **360 STM32L0 commercial identities** closed by L0.4.

It publishes Device Catalog identity availability only. It does **not** claim Flash programming-algorithm equivalence, Flash geometry equivalence, option/security semantics, PPU qualification, Socket qualification, electrical/HIL qualification, or runtime programming support.

## Frozen input

L0.4 closed the bounded commercial surface at:

- 99 Base Devices;
- 360 manufacturer-verified Active exact ICPNs;
- 360 metadata-ready exact ICPNs;
- 360 unique OpenOCD ordering-pattern routes;
- 360 capability-admittable exact ICPNs;
- 0 ambiguous, 0 unmapped, 0 capability-unresolved.

Exact published set SHA-256:

`8c7f0cc10829ff5e1ceb98cf6783247a5f685a9f1407dbd560a350348c0a521b`

Frozen L0.4 admission-plan Git blob:

`d46b7491ca34fa9d5c8b3adfb16709e9698e417e`

Frozen L0.4 admission-plan SHA-256:

`2f4fb41c427e7cea335272a42ebd14c57af08a4a056ca0b73b151fb0725382b2`

## Production prestate

The publication transaction retains an immutable copy of the Production manifest before STM32L0 publication:

`stm32l0-phase-l0.4-production-manifest-prestate.json`

- Git blob: `8abfcc870e51ac4232cdf8d807828cfe4ff5662d`
- SHA-256: `15f9c9a9be8640bc0664b562c667f676d0084e4c157e01f582c87a10886c5420`

Prestate:

```text
Production exact ICPNs: 912
Production Base Devices: 293
STM32 families: 10
STM32L0 Production: 0
```

## Deterministic publication result

Canonical dataset:

`stm32l0-commercial-icpn.csv`

- exact ICPNs: **360**
- Base Devices: **99**
- Git blob: `8484a3ca22ae141621247e1a947b993803710467`
- SHA-256: `2a40e482b0e9084feb930b94fd2cac7029d8ecbdf4b69743f99d1e5a3c2439b7`

Every published row retains:

- manufacturer identity from retained L0.2 official-ST evidence;
- metadata from L0.3 official ST Ordering Information;
- one deterministic L0.4 OpenOCD ordering-pattern route to `tcl/target/stm32l0.cfg`;
- exact commercial ICPN identity, including packing/options suffix semantics.

The publication does not convert OpenOCD routing into a physical programming claim.

## Publication artifacts

Proposal:

- Git blob: `f225f3a5c457024aa16bff7ac700db3570f41be7`
- SHA-256: `061e60ec3678d41edb182f0274ff64d935af3b026b50e4a144b2527e45652bb0`

Audit:

- Git blob: `03de66dd75f0d2b881fe45a4284e46a33bebfa00`
- SHA-256: `62be237f9f012e12fcb5605f8831d2954ec02907cdbb43671333b8e3f9cc44e6`

Publication baseline:

- Git blob: `61d49d3517c7351bec38973c116dfd1c925807e4`

Post-publication Production manifest:

- Git blob: `4e6a53695e86729063acd8ae102f66cc7eeb06c8`
- SHA-256: `c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec`

## Production poststate

```text
Production exact ICPNs: 1272  (delta +360)
Production Base Devices: 392 (delta +99)
STM32 families: 11            (delta +1)
STM32L0 Production: 360
```

This is a **catalog availability** count. It must not be presented as 360 physically qualified programmer targets.

## Historical phase replay after publication

L0.5 necessarily changes current Production state. L0.3 and L0.4 were therefore corrected to replay their immutable pre-publication Production snapshot rather than current Production. Their frozen semantic outputs remain unchanged:

- L0.3: 360 metadata-ready / 0 manual / 0 reject;
- L0.4: 360 capability-admittable / 0 unresolved.

Cross-family prioritization remains a current-state policy and therefore advances after STM32L0 enters Production:

- STM32L0 is removed from the research candidate pool;
- current standard shortlist becomes `STM32L1`, `STM32L4`;
- no new family is automatically selected.

## Permanent validation

- `publish_stm32l0_phase_l0_5.py`
- `test_stm32l0_phase_l0_5_publication.py`
- `validate_stm32l0_phase_l0_5_publication.py`
- `stm32l0-phase-l0.5-publication-proposal.json`
- `stm32l0-phase-l0.5-publication-audit.json`
- `stm32l0-phase-l0.5-publication-baseline.json`
- `.github/workflows/device-catalog-stm32l0-l05-publication-validation.yml`

The permanent L0.5 workflow is read-only. Bootstrap write permission was removed after deterministic materialization; subsequent drift fails closed rather than being auto-repaired.

## Explicit non-claims

All remain false:

- programming algorithm equivalence;
- Flash geometry equivalence;
- option/security programming qualification;
- physical target qualification;
- PPU physical validation;
- Socket physical validation;
- HIL qualification;
- runtime programming support.
