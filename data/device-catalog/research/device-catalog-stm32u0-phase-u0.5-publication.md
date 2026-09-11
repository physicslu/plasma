# Device Catalog — STM32U0 Phase U0.5 Controlled Publication

## Status and scope

Phase U0.5 is the controlled canonical + Production publication transaction for the exact 68 STM32U0 commercial identities closed by U0.4.

It publishes catalog identity availability only. It does **not** claim programming-algorithm equivalence, Flash-controller/geometry equivalence, option/security semantics, physical target qualification, HIL qualification, or PPU/runtime programming support.

## Frozen inputs

U0.5 consumes only previously closed evidence and plans:

- U0.4 admission-plan SHA-256: `525fc7301c470fbf3f38b4ddb5d1a4effac5c47da343b1ca43654d6278bbbe94`;
- U0.3 immutable Production prestate SHA-256: `93c2a4541daeb1d4aa1dcc57edef54042862eb6d9da03e3a6b401e4b8481b11d`;
- U0.3 immutable Production prestate Git blob: `34ad9299ff0c063a8c8b5de1c253dfee47b63428`;
- pre-publication Production state: 635 exact ICPNs / 217 Base Devices / 8 STM32 families;
- STM32U0 rows before publication: 0.

The transaction cannot discover additional identities, reinterpret manufacturer lifecycle state, alter U0.3 metadata semantics, or weaken the U0.4 routing gate.

## Deterministic publication result

The exact U0.4 admission set is rendered through the generic canonical writer.

| Dimension | U0.5 result |
| --- | ---: |
| Published exact STM32U0 ICPNs | 68 |
| Published STM32U0 Base Devices | 26 |
| Capability unresolved | 0 |
| Production exact ICPNs after | 703 |
| Production Base Devices after | 243 |
| Production STM32 families after | 9 |

The published canonical dataset is:

- `stm32u0-commercial-icpn.csv`
- SHA-256 `6a18ec5c8501e08a3bedd3a7bc21fdb8ece1afb4c92464aadc0d7aecfc944a75`
- Git blob `df9f8901e0d455dd2da497c5c0ec347f8052eb1b`

The post-publication Production manifest is:

- SHA-256 `903476d41997f9d20c237bccea0ee1e085fc343730e0d3740b2b82b0de0462b0`
- Git blob `89cbaa8807daf8f9c55bc8c1ca0bc1c05eaec1fc`

The frozen publication proposal SHA-256 is:

`3518b3c8f42f670e5b50c46ebe7daa42b3eb58452d9c00fd9fd2e313a5900bda`

The publication audit SHA-256 is:

`67995a36adef4ceeac91ea3afb1bf505941f6e0d36a0748da935e314133a4ef5`

## Transaction mechanics

`publish_stm32u0_phase_u0_5.py` independently replays the historical U0.4 full plan from the frozen U0.3 Production prestate, renders the exact 68 canonical rows, constructs the post-publication manifest, and compares all expected hashes.

The committed publication bytes were produced by a branch-only GitHub runner using the same repository code rather than manually transcribed rows. The temporary generator workflow is not part of the final transaction surface.

Post-publication verification hard-locks:

- exact 68-ICPN identity equality with the frozen U0.4 admission set;
- exactly 26 STM32U0 Base Devices;
- canonical CSV SHA-256 and Git blob;
- Production manifest SHA-256 and Git blob;
- proposal and audit digests;
- historical U0.4 semantic replay;
- canonical writer idempotency;
- current published canonical cannot be re-admitted;
- package-dependent `M` semantics and `TR` commercial packing identity.

## Important edge controls

The publication preserves the U0.4 distinctions:

- `STM32U073M8I6` → UFBGA81 / `STM32U073M8Ix`;
- `STM32U073M8T6` → LQFP80 / `STM32U073M8Tx`;
- `STM32U083CCT6TR` remains the exact commercial identity with `option_suffix=TR` while routing through the bounded ordering pattern.

CMSIS aliases remain blank in canonical commercial rows and are not promoted to exact commercial identities.

## Authority boundary after publication

After U0.5, `Production` means these 68 exact commercial identities are admitted to the Production Device Catalog with manufacturer-backed metadata and deterministic routing identity.

It still does **not** mean Plasma can physically program them.

The following remain explicitly unclaimed:

- programming algorithm equivalence;
- Flash controller / geometry qualification;
- option-byte / security semantics;
- electrical/socket qualification;
- real-target HIL qualification;
- PPU/runtime programming support.
