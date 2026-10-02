# STM32F7 Current Active Exact Gap Lock v3.4

Research-only preparation for the next ST Device Catalog Layer-1 expansion.

## Current state

- official ST eStore current Active exact STM32F7 MPNs: **173**
- current Production STM32F7 exact ICPNs: **19**
- current Active exact gap: **154**
- current F7 Active identity coverage: **19 / 173 = 10.9827%**

The Active population is tied to the already-locked ST eStore v1.3 reconciled artifact:

- workflow run: `36797087427`
- head: `5b016c0fd54cb186080806efd3f2660472f5b6a4`
- artifact: `11134202297`
- artifact ZIP SHA-256: `663d733cd6112bcffa4f7cf3d436b8a6e98ea91039e17dfb8493d8c4dbaf7d1d`

This deliberately preserves the same **4,550 current-Active denominator** used by the existing ST coverage program.

## Exact-set locks

- reconstructed 173-row Active set SHA-256:
  `1b4b4692ed4a4f98984d2474e498ed8593739c093e7fb403bb966fcf70f7a736`
- 154-row Active-minus-Production gap SHA-256:
  `ec93408ecec154bf40a6fcd4d5ddb063e5e36cb023bc19bbed13b306a3b4a931`

Missing exact identities span 14 series:

| Series | Gap |
| --- | ---: |
| STM32F722 | 18 |
| STM32F723 | 12 |
| STM32F730 | 5 |
| STM32F732 | 4 |
| STM32F733 | 4 |
| STM32F745 | 14 |
| STM32F746 | 22 |
| STM32F750 | 3 |
| STM32F756 | 8 |
| STM32F765 | 27 |
| STM32F767 | 19 |
| STM32F769 | 5 |
| STM32F777 | 11 |
| STM32F779 | 2 |

STM32F778 has one current Active exact identity and it is already in Production, so it contributes no gap.

## Boundary

This gate locks only the next Layer-1 identity candidate set. It does not claim:

- metadata authority replay is complete;
- backend/OpenOCD applicability for the 154 rows;
- Programming Profile support;
- Engineering Verified status;
- operational/field evidence;
- PS/HIL qualification;
- Production publication authorization.

The existing 19-row STM32F7 Production source remains unchanged.

## Potential coverage effect

Only if all 154 rows later pass metadata replay and receive explicit Production approval:

- Production exact ICPNs: **4,088 → 4,242**
- whole-ST current Active intersection: **4,009 → 4,163**
- whole-ST current Active gap: **541 → 387**
- whole-ST Active identity coverage: **88.1099% → 91.4945%**

## Next gate

Replay all 154 missing exact identities against official ST STM32F7 Ordering Information authority. Package-specific pin semantics must remain fail-closed; no backend route is required for Layer-1 metadata admission.
