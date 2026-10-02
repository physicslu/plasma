# STM32H5 Layered Gap Gate v2.6

Research-only continuation after the approved STM32F1 Layer-1 Production publication.

## Purpose

Measure the remaining STM32H5 coverage gap without conflating four separate support layers:

1. Device Catalog identity/metadata
2. Programming backend/profile
3. Engineering verification
4. Operational/field evidence

This gate makes **no Production write**.

## Frozen inputs

- official ST eStore Active exact MPN ledger: `st-stm32h5-active-exact-mpn-v1.2.txt`
- exact Active identities: **190**
- retained ST Open Pin MX1 STM32H5 XML patterns: **151**
- current Plasma OpenOCD target catalog: `plasma_openocd_target_catalog.csv`

## Layer 1 — identity / structural crosswalk

All **190/190** current Active exact STM32H5 MPNs match exactly one retained STM32H5 MX1 structural pattern after only the explicit `TR` shipment suffix is removed for structural matching.

- exact MPNs: **190**
- structural patterns: **151**
- exact identities matched: **190**
- distinct patterns exercised: **151**
- unmatched: **0**
- ambiguous: **0**
- `TR` exact identities: **51**
- non-`TR`: **139**

Observed exact-identity cohort counts:

| Cohort | Exact MPNs |
| --- | ---: |
| STM32H50 | 14 |
| STM32H52 | 39 |
| STM32H53 | 14 |
| STM32H54 | 4 |
| STM32H55 | 2 |
| STM32H56 | 59 |
| STM32H57 | 23 |
| STM32H5E | 22 |
| STM32H5F | 13 |

The 34 unexercised MX1 patterns are only classified as absent from the current Active exact ledger. This gate does not infer NRND, obsolete, future, or invalid lifecycle state from that absence.\n\nThis proves deterministic structural identity correspondence only. It does **not** yet prove Production metadata admission readiness.

## Layer 2 — current Plasma backend route

The current Plasma OpenOCD target catalog contains **no STM32H5 entry**.

Therefore this gate records:

- mapping candidates: **0**
- `no_mapping`: **190**
- synthesized route: **none**

Backend absence is not used to invalidate the manufacturer-observed Layer-1 identity set. Conversely, the existence of STM32H5 support in any external or newer backend must not be inherited into Plasma without a separately pinned and qualified backend transaction.

## Claims deliberately kept false

- metadata authority replay complete: **false**
- Catalog admission ready: **false**
- Programming Profile applicability expanded: **false**
- Engineering Verified: **false**
- operational/field evidence: **false**
- Production write authorized: **false**

## Next gate

Bind official ST Ordering Information authority for the H503/H52/H53/H54/H55/H56/H57/H5E/H5F surfaces, then replay all 190 exact identities for package, pin-count, Flash-size, temperature and option semantics.

Layer-2 remains `no_mapping` unless a separately pinned current Plasma backend route is qualified.

Only after the metadata replay can a reviewable Layer-1 admission proposal be prepared. Production publication remains a separate explicit owner-approval transaction.
