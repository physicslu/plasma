# STM32C5 Metadata Authority Replay v4.2

Research-only continuation of the locked **172 current-Active exact STM32C5 MPNs**.

## Objective

Separate Device Catalog Layer-1 metadata readiness from the unresolved C5 backend / ST-LDR route.

The earlier DFP crosswalk observed:

- **139** exact DFP variants
- **33** commercial exact MPNs with only a DFP parent-device match
- **0** Production backend routes

That DFP freshness split is not treated as a Layer-1 metadata blocker.

## Ordering authority

The replay binds official ST ordering tables:

- STM32C531 / C532 — DS15125 Rev 1
- STM32C542 — DS15135 Rev 1
- STM32C551 / C552 — DS14928 Rev 1
- STM32C562 — DS14927 Rev 1
- STM32C591 / C593 — DS15136 Rev 1
- STM32C5A3 — DS15137 Rev 1

## Result

- Active exact identities: **172**
- metadata decoded: **172/172**
- blocked: **0**
- direct Ordering Information: **170**
- exact-MPN bounded exceptions: **2**
  - `STM32C551CCT7`
  - `STM32C551CCT7TR`

Those two `7` temperature-code variants are bounded to the exact official ST eStore rows showing -40..105 C. The exception is not generalized to other C55 variants.

The 33 DFP parent-only identities are all metadata-decodable through the exact eStore identity plus official ordering-code authority.

## Boundary

This does **not** claim:

- C5 OpenOCD / ST-LDR route readiness
- Programming Profile applicability
- Engineering Verified
- field evidence
- PS/HIL qualification
- Production write authorization

## Next gate

Prepare a reviewable **172-row STM32C5 Layer-1 admission proposal**, with every backend route left unbound.
