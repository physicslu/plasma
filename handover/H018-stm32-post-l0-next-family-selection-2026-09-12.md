# H018 — STM32 Post-L0 Next-Family Selection

**Date:** 2026-09-12
**Status:** Gate 1 implementation complete; PR #517 Gate 2 candidate after final-head recheck
**Primary workstream:** Device Catalog / STM32 next-family research selection
**Repository:** `physicslu/plasma`
**Branch:** `agent/device-catalog-post-l0-next-family-selection`
**PR:** #517

## 1. Starting state

STM32L0 L0.5 merged in PR #516 at:

`db2122c1cf57b8eff4207d94e40cd99f9fff4391`

Production after L0 publication:

```text
exact ICPNs:        1272
Base Devices:        392
STM32 families:       11
STM32L0 exact:       360
```

The current read-only structural shortlist is:

1. STM32L1
2. STM32L4

No family was selected before this transaction.

## 2. Gate 1 boundary

Gate 1 authorized **STM32 Post-L0 — Next-Family Selection**.

Authorized:

- freeze the post-L0 Production prestate;
- replay current cross-family prioritization against that immutable prestate;
- reuse and hard-lock retained official-ST L1/L4 commercial identity/lifecycle evidence;
- reuse and hard-lock retained official-ST L4 Ordering Information evidence;
- deterministically select the next research family;
- add tests, negative controls, CI, report and handover;
- prepare PR #517 for Gate 2.

Not authorized:

- new ICPNs;
- Production writes;
- canonical admission/publication;
- programming policy;
- Flash algorithm/geometry equivalence;
- option/security qualification;
- PPU/Socket/electrical/HIL qualification;
- runtime programming-support claims.

## 3. Immutable Production prestate

Retained file:

`data/device-catalog/research/stm32-post-l0-production-manifest-prestate.json`

Hashes:

- Git blob: `4e6a53695e86729063acd8ae102f66cc7eeb06c8`
- SHA-256: `c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec`

Historical replay is deliberately isolated from future current-Production changes.

## 4. Retained official-ST evidence

Commercial identity/lifecycle evidence:

`data/device-catalog/research/evidence/stm32-l1-l0-l4-post-c0-live-2026-09-12/probe-summary.json`

SHA-256:

`45c3020462601e6cb36e726cc1acc4203abc36a96063a5223ab5c7511bcff02c`

Current-candidate result:

```text
STM32L1: 4 representatives / 1 Active / 3 lifecycle-excluded / 1 Active exact / 8 excluded non-Active exact
STM32L4: 24 representatives / 24 Active / 0 lifecycle-excluded / 60 Active exact / 3 excluded non-Active exact
```

STM32L1 remains deprioritized for the next-family transaction but is not rejected for future support.

Ordering Information review:

`data/device-catalog/research/stm32-l0-l4-post-c0-ordering-authority-review.json`

SHA-256:

`d16e71cb322c7da754ed12cc1bd0e984015888cbf8bdb07685e1d87966ad8612`

STM32L4 remains complete across 24/24 representative targets with 20 official datasheets, zero blocking issues, and `revision_drift=false`.

## 5. Deterministic selection

Frozen artifact:

`data/device-catalog/research/stm32-post-l0-next-family-selection.json`

Hashes:

- Git blob: `7b189171a2ce241387599541ff7d7e9744509a45`
- SHA-256: `70dd86816606e94380fe6a0b0474a88771542607fc7db2aaa3a8be65e1e2e7b8`

Result:

`selected_next_research_family = STM32L4`

Selection status:

`selected_only_remaining_active_clean_candidate_after_lifecycle_and_ordering_evidence`

This selection does **not** reuse the old post-C0 tie-break. A negative control makes both L1 and L4 Active-clean and requires the transaction to block for a new comparison rather than silently select by stale order.

## 6. Validation

Dedicated workflow:

`.github/workflows/device-catalog-stm32-post-l0-selection-validation.yml`

The first run exposed one negative-control ordering issue: multiple Active candidates reached Ordering review before the explicit multiple-candidate block. The control flow was corrected so multiple Active-clean candidates fail closed before any stale comparison is reused.

After correction:

- post-L0 next-family selection validation — SUCCESS
- deterministic selection — STM32L4
- Production writes — 0

Final repository-wide CI still requires recheck after documentation/handover commits.

## 7. Production boundary

This phase performs zero Production writes:

```text
Production exact ICPNs: 1272 (delta 0)
Production Base Devices: 392 (delta 0)
Production families: 11 (delta 0)
STM32L0 Production: 360
```

Selection is research prioritization only; it does not establish physical programming support.

## 8. Next action

Recheck PR #517 final head, current `main`, all applicable CI, compare state, reviews and review threads. If merge-ready, request explicit **Gate 2 merge approval**.

After this selection merges, a future STM32L4 foundation/discovery transaction requires a new Gate 1.
