# STM32L5 — Manufacturer-Authoritative Identity Discovery

Status: **bounded commercial identity discovery complete; research-only; Production unchanged**

## Scope

This transaction consumes the merged STM32L5 security-scope foundation and discovers exact commercial identities from official ST product surfaces.

The bounded family surface is the official STM32L5x2 product selector. On 2026-09-14 it exposed 17 Base Devices across STM32L552 and STM32L562. Exact commercial identity and lifecycle are taken only from the corresponding ST **Quality & Reliability** Part Number rows.

No exact ICPN is synthesized from datasheet ordering patterns. Ordering patterns and OpenOCD remain research/routing evidence only.

## Frozen result

- Base Devices: **17**
- Exact ICPNs: **49**
- Observed marketing status: **49 Active / 0 retained non-Active**
- Source-unavailable exclusions: **0**
- Manual intervention: **0**
- Base Device set SHA-256: `a49212731437f33674abc0c5c6a90697bbc3e377f997c618a66fb96b51632435`
- Exact ICPN set SHA-256: `f9a74a7badfb39f8fc52753fc3904cd63a8b3e0a2e4dcc37dee759809aaa68b1`

The retained exact set is in `stm32l5-commercial-identity-discovery.csv` and the frozen replay contract is `stm32l5-manufacturer-identity-discovery.json`.

## Evidence semantics

`Active` is an observation of the manufacturer page at the retained observation date. It is **not** a permanent lifecycle guarantee. Future lifecycle changes require a separately governed refresh; they do not silently rewrite this retained transaction.

The STM32L552ZC leaf is included because the official ST product page / Quality & Reliability surface exposes the exact identity `STM32L552ZCT6Q`, even though one canonical URL path intermittently returned an access error during research. The identity itself was confirmed on ST-controlled product surfaces.

## Security fence

The parent security-scope foundation remains authoritative. This discovery does not authorize or validate:

- Production catalog admission;
- TZEN or option-byte writes;
- RDP regression or mass erase;
- TrustZone/security semantics;
- Flash geometry;
- programming algorithm equivalence;
- external-Flash behavior under TrustZone;
- runtime programming support;
- HIL validation.

Identity completeness and runtime/security support are independent dimensions.

## Next research gate

The next bounded transaction is **STM32L5 metadata policy**. It may normalize identity metadata needed by the catalog, but must preserve exact manufacturer identity and the security fence. Production publication remains a later, separately approved gate.
