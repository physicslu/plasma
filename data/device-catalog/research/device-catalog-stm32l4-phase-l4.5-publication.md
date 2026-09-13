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

L4.5 normalizes the frozen L4.3 research verification labels into the established Production runtime `verified_*` provenance vocabulary. This is a publication-schema translation only; it does not change manufacturer evidence, identity scope, metadata values, or L4.4 routing decisions.

Canonical hard lock:

- Git blob: `6cbb7ee5f5189c7d510623940a8945a2bde38399`
- SHA-256: `f9ab12f70221a7a6fd934e977d2bed2fed7bdca8fdee9208aaf0a5082533793c`

Publication proposal:

- Git blob: `24a3166fe302e60a184f8623a164e2a2df3b7afd`
- SHA-256: `b390447109da6f836e06722a050cdec7c883f695d7f1df7c8be64eab356790d7`

Publication audit:

- Git blob: `9bd87bffea6880bfa2e2d373f5ac0c33e02625da`
- SHA-256: `0c6a0d9ebdc5d97a7238333592f298d786000df1b466e698996695192fe12053`

Publication baseline Git blob:

`d43143e3f48a75c886810be1fc7b70061cc3966c`

Post-publication Production manifest:

- Git blob: `1aa2311a25a69742c428147a402816ed5071e04e`
- SHA-256: `b88adcb38f0833a25da1671592ea98496d61166b9d0e51877ffb92ad2820b9fe`

## Production poststate

```text
Production exact ICPNs: 1718  (delta +446)
Production Base Devices: 530 (delta +138)
STM32 families: 12              (delta +1)
STM32L4 Production: 446
```

The 446 published rows are catalog identities. They are not 446 physically qualified programmer targets.

## Manufacturer exception continuity

The three exact L4.3 manufacturer-authority exceptions remain explicit in canonical provenance and do not expand identity scope:

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
- `test_stm32l4_phase_l4_5_publication.py` verifies identity set, canonical semantics, runtime-compatible provenance, manufacturer-exception continuity, Production binding, and non-claim boundaries.
- `validate_stm32l4_phase_l4_5_publication.py` hard-locks all materialized publication bytes.
- `.github/workflows/device-catalog-stm32l4-l45-publication-validation.yml` provides permanent read-only CI.

Temporary write-capable materialization workflows removed themselves after committing deterministic outputs.
