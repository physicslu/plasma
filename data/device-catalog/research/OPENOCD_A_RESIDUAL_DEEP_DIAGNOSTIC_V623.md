# OpenOCD A-Residual Deep Diagnostic v6.23

Research-only analysis of the **8 exact ICPNs** remaining in Tier A after v6.21 and the v6.22 rebaseline.

## Exact scope

STM32C0:
- STM32C011D6Y6TR
- STM32C051D8Y6TR
- STM32C091ECY6TR
- STM32C092ECY3TR
- STM32C092ECY6TR

STM32G4:
- STM32G491RCY6TR

STM32L4:
- STM32L496WGY6PST
- STM32L496WGY6PTR

## Structural result expected

Seven rows (five C0 and two L4) are exact commercial identities with same-series mapped siblings, but their exact **base variants are absent from canonical route inventory**.

The G4 row is different: the same base device already has mapped I/T package ordering patterns, while the Y/WLCSP identity is not uniquely resolved by the diagnostic package-position probe. A generic package-letter substitution is therefore explicitly forbidden.

## Next gates

- C0 + L4 (7): expand canonical route inventory only from authoritative ordering evidence for these exact base variants.
- G4 (1): obtain authoritative evidence that uniquely binds the Y/WLCSP package variant before any bounded bridge is proposed.

No identifier is inferred here. No Production write, Programming Profile binding, erase/program/verify, Engineering Verified, or HIL claim is made.
