# STM32F1 Layer-1 Production Publication v2.5

**Approved Production Catalog transaction.**

Owner approval was received for the complete v2.4 proposal: **205 current Active STM32F1 exact MPNs**.

## Publication result

| State | F1 post-state |
| --- | ---: |
| Production exact ICPNs | **280** |
| current Active exact ICPNs covered | **275 / 275** |
| Layer-2 mapped | **280** |
| Layer-2 `no_mapping` | **0** |
| Programming Profile bound exact ICPNs | **2** |
| Engineering Verified | not claimed |

Five historical F1 Production identities remain outside the current Active set, so F1 Production count is 280 while current Active coverage is 275/275.

Every one of the 205 approved additions uses the existing F1 CMSIS/Base Device mapping model and resolves to `tcl/target/stm32f1x.cfg`.

## Programming Profile boundary

The existing binding set `stm32f103c-pilot-v0` remains exactly:

- `STM32F103C8T6`
- `STM32F103CBT6`

No newly published F1 identity receives Programming Profile applicability merely because it belongs to STM32F1 or STM32F103.

## Historical replay boundary

The previous 75-row Phase 2.9 post-admission F1 canonical state is retained as the immutable file `stm32f1-phase2.9-post-admission-canonical.csv`. Historical Phase 2.7/2.9 tests replay against that snapshot; current Production validation uses the 280-row canonical file.

## Approved effect at publication time

- Production exact total: **3,511 -> 3,716**
- current Catalog backend partition: **3,673 mapped / 43 no_mapping**
- whole-ST current Active intersection: **3,432 -> 3,637**
- whole-ST current Active gap: **1,118 -> 913**
- whole-ST current Active identity coverage: **75.4286% -> 79.9341%**

This does not create Engineering Verified, field evidence, PS/HIL qualification, or new Programming Profile applicability.

## Integrity

- approved exact-set SHA-256: `a4f4fc7db33bf5be34f6f114e266474625cd63cb8ba9719f103535c7036b26e4`
- approved proposal CSV SHA-256: `33410a8f941d7d88ffb90f81d9859e04d10e0e3f40bfd6a57a05d1603f4f4287`
- approved authority SHA-256: `5b075a65dec2590bea8df1b93a47448efb4c88f1072b8a277c6659a482a0e376`
- published F1 canonical SHA-256: `a2b9463d58d434ff4792f1830b4e6d0fbe75ea3d084568801402aa799c91b0c4`
- published F1 Git blob: `c3219788d61591a63aae8cd8df3d25ef15d5c8f3`
