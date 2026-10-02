# STM32F3 Current Active Exact Gap Lock v3.0

Research-only preparation for the next ST Device Catalog Layer-1 expansion.

## Current state

- official ST eStore current Active exact STM32F3 MPNs: **192**
- current Production STM32F3 exact ICPNs: **10**
- current Active exact gap: **182**
- current F3 Active identity coverage: **10 / 192 = 5.2083%**

The 192-row Active set is reconstructed from the already-locked ST eStore v1.3 reconciled artifact:

- workflow run: `36797087427`
- head: `5b016c0fd54cb186080806efd3f2660472f5b6a4`
- artifact: `11134202297`
- artifact ZIP SHA-256: `663d733cd6112bcffa4f7cf3d436b8a6e98ea91039e17dfb8493d8c4dbaf7d1d`

This intentionally reuses the same 4,550-part denominator rather than mixing a newer manufacturer snapshot into the locked coverage baseline.

## Exact-set locks

- 192-row Active set SHA-256: `e3149bf214375dd50c20919fb2b42ec127626ba6440f62ea90f62e7fe6cde641`
- 182-row Active-minus-Production gap SHA-256: `1514c8edd3d190a8fd2bc9c27960c47f05ab4536640e008d73e4d5ab2f5a01d7`

Series distribution of the **182 missing** exact identities:

| Series | Gap |
| --- | ---: |
| STM32F301 | 21 |
| STM32F302 | 50 |
| STM32F303 | 55 |
| STM32F318 | 2 |
| STM32F328 | 1 |
| STM32F334 | 23 |
| STM32F358 | 3 |
| STM32F373 | 21 |
| STM32F378 | 5 |
| STM32F398 | 1 |

## Boundary

This lock establishes only the exact Layer-1 candidate set.

It does **not** claim:

- metadata authority replay is complete;
- backend/OpenOCD applicability;
- Programming Profile support;
- Engineering Verified status;
- HIL or field evidence;
- Production publication authorization.

The historical F3 policy covered only 10 exact MPNs across a bounded six-Base-Device surface. It must not be generalized to these 182 rows without a new authority replay.

## Potential coverage effect

Only if all 182 later pass metadata replay and receive explicit Production approval:

- Production exact ICPNs: **3,906 → 4,088**
- whole-ST current Active intersection: **3,827 → 4,009**
- whole-ST current Active gap: **723 → 541**
- whole-ST Active identity coverage: **84.1099% → 88.1099%**

## Next gate

Expand official ST Ordering Information authority across all ten current Active F3 series, then replay all 182 missing exact identities fail-closed before preparing a Layer-1 admission proposal.
