# STM32 Post-L0 Next-Family Selection

## Scope

This transaction selects the next STM32 **research family only** after STM32L0 L0.5 controlled publication.

It does not:

- add or publish ICPNs;
- modify Production;
- define programming policy;
- prove Flash programming-algorithm or geometry equivalence;
- qualify option/security behavior;
- qualify PPU, Socket, electrical, or HIL behavior;
- claim runtime programming support.

## Frozen Production prestate

The transaction is bound to `stm32-post-l0-production-manifest-prestate.json`:

```text
Production exact ICPNs: 1272
Production Base Devices: 392
STM32 families: 11
STM32L0 Production: 360
```

- Git blob: `4e6a53695e86729063acd8ae102f66cc7eeb06c8`
- SHA-256: `c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec`

The selection validator replays this immutable snapshot instead of binding future current Production state.

## Current shortlist

Post-L0 cross-family prioritization deterministically yields:

1. `STM32L1`
2. `STM32L4`

No family is selected by the prioritization layer itself.

## Manufacturer-authoritative evidence

The transaction reuses the retained official-ST post-C0 evidence acquisition because it already contains both current candidates and is hard-locked:

`evidence/stm32-l1-l0-l4-post-c0-live-2026-09-12/probe-summary.json`

Evidence authority:

`official_st_quality_and_reliability_exact_identity_plus_sample_and_buy_marketing_status_exact_set_join`

Retained summary SHA-256:

`45c3020462601e6cb36e726cc1acc4203abc36a96063a5223ab5c7511bcff02c`

Current candidate disposition:

```text
STM32L1: 4 representatives / 1 Active / 3 lifecycle-excluded / 1 Active exact / 8 excluded non-Active exact
STM32L4: 24 representatives / 24 Active / 0 lifecycle-excluded / 60 Active exact / 3 excluded non-Active exact
```

STM32L1 is **deprioritized**, not rejected for future support.

## Ordering Information authority

Retained official-ST review:

`stm32-l0-l4-post-c0-ordering-authority-review.json`

SHA-256:

`d16e71cb322c7da754ed12cc1bd0e984015888cbf8bdb07685e1d87966ad8612`

For STM32L4:

```text
representative targets: 24
unique official datasheets: 20
ordering authority covered targets: 24
required schema complete targets: 24
blocking issues: 0
revision drift: false
ordering evidence quality: complete
```

Because STM32L1 is already lifecycle-deprioritized, no current L1 Ordering Information comparison is required to select the only remaining Active-clean candidate.

## Deterministic selection

Frozen selection:

`stm32-post-l0-next-family-selection.json`

- Git blob: `7b189171a2ce241387599541ff7d7e9744509a45`
- SHA-256: `70dd86816606e94380fe6a0b0474a88771542607fc7db2aaa3a8be65e1e2e7b8`

Result:

`selected_next_research_family = STM32L4`

Selection status:

`selected_only_remaining_active_clean_candidate_after_lifecycle_and_ordering_evidence`

The negative control intentionally blocks if STM32L1 and STM32L4 both become Active-clean. The transaction will not silently reuse the older post-C0 shortlist tie-break.

## Authority boundary

All selection authority-boundary flags remain `false`, including Production writes, exact-ICPN publication, programming policy, Flash/security qualification, PPU/Socket physical validation, HIL, and runtime programming support.

Production remains:

```text
1272 exact ICPNs (delta 0)
392 Base Devices (delta 0)
11 STM32 families (delta 0)
```

A future STM32L4 foundation/discovery transaction requires a new Gate 1.
