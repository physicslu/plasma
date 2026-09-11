# STM32U0 Phase U0.2 — Manufacturer-Authoritative Commercial Discovery

**Status:** merge-ready evidence transaction pending final CI  
**Primary workstream:** ICPN  
**Scope:** research evidence only; no Production admission

## Objective

Expand the frozen U0.1 STM32U0 ordering-pattern surface into the complete deterministic
commercial discovery boundary and retain manufacturer-authoritative exact part-number /
lifecycle evidence without inferring programming support.

The U0.1 surface contains 42 `ordering_pattern` rows and 6 `cmsis_device_name` aliases.
The 42 ordering rows deterministically collapse to 26 unique Base Devices:

- STM32U031: 10
- STM32U073: 12
- STM32U083: 4

The six CMSIS aliases remain excluded from commercial identity authority.

## Manufacturer authority

U0.2 uses the official ST product-page **Quality & Reliability** table as the
commercial identity/lifecycle authority because exact `Part Number` and
`Marketing Status` occur in the same manufacturer-controlled row.

The dynamically rendered Sample & Buy table is not an identity gate. An earlier
dual-surface attempt exposed two empty Sample & Buy status cells even though the
corresponding Quality & Reliability rows were explicitly Active; U0.2 therefore
removed that UI-rendering dependency rather than inferring missing lifecycle values.

OpenOCD remains a bounded-surface and historical routing source only. It never gates
commercial identity.

## Final authoritative run

- PR head: `d08b4fe2d6b9de772204e9530af5410f71351f18`
- executed synthetic merge SHA: `80a6312e04db2876ff68f64125b99dda11b53691`
- workflow run: `34545996184`
- artifact: `10179167672`
- artifact SHA-256: `2296dca761deaee6a72895bf9ba489fb70295d11654a7c69df339b91a9ea995a`
- acquisition window (UTC): `2026-09-11T00:20:01Z` to `2026-09-11T00:25:33Z`
- browser: Chromium `151.0.7922.34`
- evidence profile: `stm32u0_quality_reliability_v1`

Result:

- 26 / 26 Base Devices acquired successfully
- 26 Active-candidate targets
- 68 unique Active exact ICPNs
- 0 acquisition failures
- 0 manual-review targets
- 0 source-unavailable / HTTP-404 exclusions
- 0 lifecycle-only targets
- 0 excluded non-Active part numbers
- 26 / 26 historical OpenOCD routing observations unique
- routing never gates commercial identity

The three frozen U0.1 representative controls showed no exact-ICPN drift:

- STM32U031C6
- STM32U073C8
- STM32U083CC

## Retention

Raw browser evidence remains in GitHub Actions artifact `10179167672`.
The repository retains a compact immutable projection:

- `stm32u0-phase-u0.2-discovery-baseline.json`
- `evidence/stm32u0-u0.2-official-st-discovery-live-2026-09-11/`

The retained package binds the artifact/run/digest, PR head, synthetic merge SHA,
manufacturer acquisition window, source Git blobs, Production prestate, U0.1
continuity controls, exact ICPN lists, evidence-section/raw hashes, and routing
observations.

## Authority boundaries

U0.2 does **not** authorize or imply:

- canonical / Production admission;
- CMSIS alias == commercial identity;
- manufacturer evidence == admission;
- programming-policy definition or programming-algorithm equivalence;
- Flash-controller or geometry qualification;
- option-byte or security semantic qualification;
- physical HIL / real-IC qualification;
- runtime / PPU support.

At the U0.2 boundary, STM32U0 remains absent from Production.

## Next transaction

U0.3 may derive manufacturer-authoritative commercial metadata policy from official
STM32U0 Ordering Information. U0.3 must consume this retained identity set as evidence;
it must not silently expand or reinterpret the U0.2 commercial identity boundary.
