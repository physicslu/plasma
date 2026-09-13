# H024 — STM32L1 Lifecycle Requalification Handover

**Date:** 2026-09-13  
**Status:** Gate 1 implementation complete; PR #538 Gate 2 candidate  
**Primary workstream:** Device Catalog / STM32L1 lifecycle evidence requalification  
**Repository:** `physicslu/plasma`  
**Branch:** `agent/device-catalog-stm32l1-requalification`  
**PR:** #538

## 1. Starting state

STM32L4 L4.5 is complete and merged. The transaction boundary for this work is the frozen post-L4 Production state:

- exact ICPNs: 1,718
- Base Devices: 530
- STM32 families: 12
- STM32L4 exact ICPNs: 446
- STM32L1 exact ICPNs: 0

Current deterministic standard research shortlist: `STM32L1` only. No next family is selected.

## 2. Why requalification was necessary

The earlier cross-family evidence gate used one lexical-min official ST product page per guarded STM32L1 subfamily. That evidence was correct for those exact pages, but the method was not sufficient to infer an entire subfamily lifecycle when ST publishes legacy and generation-specific companion pages.

Lifecycle is therefore treated as an exact-variant property, not a family/subfamily property.

## 3. Gate 1 boundary

Gate 1 authorized a bounded, read-only STM32L1 official-ST evidence requalification.

Allowed:

- re-check exact commercial identity and lifecycle using official ST evidence
- check official ST Ordering Information coverage
- retain evidence and deterministic validators
- determine whether STM32L1 is eligible for a future research gate

Not allowed:

- Production write
- canonical admission/publication
- automatic next-family selection
- programming-policy or Flash-geometry claims
- option/security, electrical/socket, HIL, or runtime-support claims

## 4. Authoritative live acquisition

Official ST dual-surface acquisition completed successfully:

- workflow run: `34749400091`
- run attempt: `1`
- executed Git SHA: `b7b9ce7b7e808eae765f964c0cd6e2799887a456`
- artifact ID: `10314963393`
- artifact name: `stm32l1-requalification-live-34749400091-1`
- artifact SHA-256: `b20ffce5cf4ab540fbed1458719c544ba06cfceb8f0ba10829034b76c0dbcf5f`
- Playwright: `1.62.0`
- Chromium: `151.0.7922.34`
- 7/7 target surfaces acquired
- manual review: 0
- source unavailable: 0

Commercial identity/lifecycle authority:

- official ST Quality & Reliability: exact orderable Part Number identity
- official ST Sample & Buy: Marketing Status
- exact sets joined fail-closed

OpenOCD only bounds the research surface.

## 5. Requalification result

All four STM32L1 guarded subfamilies have current Active exact orderable evidence:

| Subfamily | Historical page | Generation/current surface | Active exact evidence |
|---|---|---|---:|
| STM32L100 | non-Active only | generation-A Active | 2 |
| STM32L151 | non-Active only | generation-A Active | 4 |
| STM32L152 | non-Active only | generation-A Active | 2 |
| STM32L162 | Active | current Active | 1 |

Total retained evidence:

- Active exact ICPNs: 9
- non-Active exact ICPNs: 8
- active subfamilies: 4/4

Historical single-page false-negative subfamilies:

- STM32L100
- STM32L151
- STM32L152

The old NRND exact-variant evidence remains valid. What is invalidated is the earlier extrapolation from one legacy page to the whole subfamily.

## 6. Ordering Information authority

Official ST Ordering Information coverage is complete for all four subfamilies:

- STM32L100 generation A: `DocID025966 Rev 6`
- STM32L151 / STM32L152 generation A: `DocID024330 Rev 5`
- STM32L162: `DS10287 Rev 6`
- generation migration authority: `TN1176`

`TN1176` establishes non-A and generation-A designations as distinct manufacturer-defined product surfaces.

## 7. Deterministic disposition

Frozen result:

`status = eligible_for_next_research_gate`

This removes the previous lifecycle-based reason to deprioritize STM32L1. It does not select STM32L1 or authorize discovery/publication.

`selected_next_research_family = null`

A separate Gate 1 is required for any STM32L1 bounded foundation/commercial discovery phase.

## 8. Permanent offline validation

Permanent assets include:

- deterministic requalification builder
- negative-control unit tests
- retained official-ST live evidence
- exact live provenance and artifact digest
- official Ordering Information authority record
- frozen post-L4 Production prestate
- hard-locked frozen result
- offline GitHub Actions validation

The temporary live-acquisition workflow was removed after evidence retention.

Historical validation is intentionally bound to the frozen post-L4 Production prestate so legitimate future Production growth does not create stale-validator failures.

## 9. Production boundary and non-claims

Production delta: **0**.

Production remains:

- 1,718 exact ICPNs
- 530 Base Devices
- 12 families
- STM32L1: 0

This transaction does not establish programming algorithm/Flash geometry equivalence, erase/program/verify behavior, option/security qualification, PPU/FPGA/SWD electrical qualification, socket correctness, real-IC HIL, or runtime programming support.

## 10. Continuation

PR #538 must be synchronized to current `main`, pass all applicable final-head CI, remain free of Production changes/blocking review findings, and receive explicit Gate 2 approval before merge.

Do not start STM32L1 discovery or any other new device-family transaction as part of Gate 2 merge/post-merge verification.
