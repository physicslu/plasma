# STM32L1 Lifecycle Requalification

## Scope

This transaction requalifies the **research eligibility** of STM32L1 after STM32L4 L4.5 publication.

It is intentionally read-only with respect to Production. It does not publish or admit any STM32L1 ICPN and does not define programming support.

## Starting state

Post-L4 Production is frozen for this transaction at:

- 1,718 exact ICPNs
- 530 Base Devices
- 12 STM32 families
- STM32L4: 446 exact ICPNs
- STM32L1: 0 exact ICPNs

The current deterministic standard research shortlist contains only STM32L1, but selection remains unset.

## Why requalification was required

The earlier post-C0 evidence gate sampled one lexical-min product page per guarded STM32L1 subfamily. That evidence correctly described those pages, but the inference was too broad: a single legacy page is not sufficient to classify the lifecycle of the entire subfamily when ST publishes generation-specific companion product pages.

The requalification therefore treats lifecycle as an **exact-variant property**, not a family or subfamily property.

## Authoritative live acquisition

Official ST dual-surface acquisition was executed in GitHub Actions:

- workflow run: `34749400091`
- run attempt: `1`
- executed Git SHA: `b7b9ce7b7e808eae765f964c0cd6e2799887a456`
- artifact ID: `10314963393`
- artifact: `stm32l1-requalification-live-34749400091-1`
- artifact SHA-256: `b20ffce5cf4ab540fbed1458719c544ba06cfceb8f0ba10829034b76c0dbcf5f`
- Playwright: `1.62.0`
- Chromium: `151.0.7922.34`
- manual review: 0
- source unavailable: 0

Commercial identity/lifecycle authority remains:

- official ST Quality & Reliability: exact orderable Part Number identity
- official ST Sample & Buy: Marketing Status
- exact Part Number sets are joined fail-closed

OpenOCD only bounds the research surface.

## Result

Seven product-page surfaces were checked: the historical representative page plus a generation companion for L100/L151/L152, and the current L162 representative.

| Subfamily | Historical page | Generation/current page | Active exact evidence |
|---|---|---|---|
| STM32L100 | non-Active only | generation-A Active | 2 |
| STM32L151 | non-Active only | generation-A Active | 4 |
| STM32L152 | non-Active only | generation-A Active | 2 |
| STM32L162 | Active | current Active | 1 |

Active exact evidence set:

- `STM32L100C6U6A`
- `STM32L100C6U6ATR`
- `STM32L151C6T6A`
- `STM32L151C6T6ATR`
- `STM32L151C6U6A`
- `STM32L151C6U6ATR`
- `STM32L152C6T6A`
- `STM32L152C6U6A`
- `STM32L162QCH6`

The retained legacy pages also contain eight exact non-Active variants.

The historical single-page method therefore produced a lifecycle **false negative at subfamily level** for:

- STM32L100
- STM32L151
- STM32L152

This does not make the old exact-variant NRND evidence wrong; it makes the old subfamily-level extrapolation invalid.

## Ordering Information authority

Official ST Ordering Information coverage is complete for all four subfamilies through:

- STM32L100 generation A: `DocID025966 Rev 6`
- STM32L151 / STM32L152 generation A: `DocID024330 Rev 5`
- STM32L162: `DS10287 Rev 6`
- official migration authority: `TN1176`

The migration note is important because it establishes non-A and generation-A product designations as distinct manufacturer-defined product surfaces.

## Deterministic disposition

`status = eligible_for_next_research_gate`

This means the prior lifecycle-based deprioritization is no longer a valid reason to exclude STM32L1 from future research.

It does **not** mean STM32L1 has been selected, discovered exhaustively, metadata-qualified, admitted, published, or programming-qualified.

`selected_next_research_family` remains `null`.

## Production boundary

Production remains unchanged by this transaction:

- exact ICPNs: 1,718
- Base Devices: 530
- families: 12
- STM32L1 Production: 0

The historical validator is bound to a frozen post-L4 Production prestate so later legitimate Production growth will not invalidate this evidence transaction.

## Explicit non-claims

This transaction does not establish:

- canonical admission
- exact ICPN publication
- programming policy
- Flash geometry equivalence
- erase/program/verify qualification
- option/security qualification
- PPU/FPGA/SWD electrical qualification
- socket/adapter qualification
- real-IC HIL
- runtime programming support

## Continuation

A separate Gate 1 is required before starting any STM32L1 bounded foundation/commercial discovery phase.
