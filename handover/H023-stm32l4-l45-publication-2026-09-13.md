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

L4.5 translates the frozen L4.3 research verification labels into the established Production runtime `verified_*` provenance vocabulary. This normalization changes no identity, metadata, manufacturer authority, or L4.4 capability decision.

Canonical hashes:

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

- Git blob: `1aa2311a25a69742c428147a402816ed5071e04e`
- SHA-256: `b88adcb38f0833a25da1671592ea98496d61166b9d0e51877ffb92ad2820b9fe`

## Integration repairs discovered by publication

L4.5 exposed three stale/current-state boundaries and one real runtime-integration contract:

1. cross-family prioritization now excludes STM32L4 from the future-family shortlist and leaves STM32L1 as the remaining standard shortlist family;
2. historical L0.5 validation now permits later Production growth while preserving its frozen bytes and original poststate hard locks;
3. historical L4.3 CI validates its frozen pre-publication manifest instead of incorrectly requiring all later transactions to have zero Production diff;
4. STM32L4 publication provenance is normalized to the canonical runtime `verified_*` contract rather than weakening the runtime loader.

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

Temporary materialization workflows removed themselves after deterministic generation; permanent CI is read-only.

## Continuation

Before Gate 2:

1. ensure PR #535 final-head applicable CI is green;
2. confirm current `main`, PR mergeability, and review/comment blockers;
3. confirm Production delta is exactly +446 STM32L4 rows and no unrelated Production change exists;
4. obtain explicit Gate 2 merge approval.

After merge, do not automatically infer physical programmer support from catalog publication. Any next STM32 family selection or hardware/runtime qualification requires its own Gate 1 scope.
