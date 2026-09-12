# H012 — STM32 Post-C0 Next-Family Evidence Selection Handover

**Date:** 2026-09-12
**Status:** Gate 1 implementation complete; final PR qualification pending
**Primary workstream:** Device Catalog / STM32 next-family research selection
**Repository:** `physicslu/plasma`
**Branch:** `agent/device-catalog-post-c0-evidence-selection`
**PR:** #504

## 1. Starting state

STM32C0 C0.5 was merged as PR #503 at merge commit:

`878e0b7b874c5aa45b55ee619e5d30531d2dd037`

Production is authoritative at:

```text
exact ICPNs:        912
Base Devices:       293
STM32 families:      10
STM32C0 exact:       209
```

The current read-only cross-family shortlist after C0 publication was:

1. STM32L1
2. STM32L0
3. STM32L4

No family was selected before this transaction.

## 2. Transaction boundary

Gate 1 authorized a bounded, read-only official-ST manufacturer-evidence accessibility comparison over L1/L0/L4.

This transaction may select the **next research family only**.

It does not:

- add or admit ICPNs
- modify Production
- define programming policy
- prove Flash algorithm or geometry equivalence
- qualify option/security behavior
- qualify socket/electrical or HIL behavior
- claim PPU/runtime programming support

Production remains 912 exact ICPNs throughout this transaction.

## 3. Deterministic representative surface

One lexical-min Base Device is selected per guarded OpenOCD ordering-pattern subfamily:

```text
STM32L1:  4
STM32L0: 16
STM32L4: 24
Total:   44
```

OpenOCD only bounds research. It is not commercial identity or lifecycle authority.

## 4. Authoritative live acquisition

Official ST dual-surface acquisition completed successfully:

- workflow run: `34674798156`
- run attempt: `1`
- acquisition targets: 44
- dispositioned targets: 44
- manual review: 0
- bounded probe complete: true
- artifact: `stm32-post-c0-live-34674798156-1`
- artifact ZIP SHA-256: `b179c6429e095b5407ddfa44779f3cbf3e84930b4f6e00d0e4bfb4027016a6c2`

Commercial evidence authority:

- Quality & Reliability: exact Part Number identity
- Sample & Buy: Marketing Status
- lifecycle is joined only when exact Part Number sets match fail-closed

Retained namespace:

`data/device-catalog/research/evidence/stm32-l1-l0-l4-post-c0-live-2026-09-12/`

Observed result:

```text
L1: 4 targets / 1 Active / 3 lifecycle-excluded / 1 Active exact / 8 non-Active exact
L0: 16 targets / 16 Active / 0 lifecycle-excluded / 44 Active exact
L4: 24 targets / 24 Active / 0 lifecycle-excluded / 60 Active exact / 3 extra non-Active exact
```

STM32L1 is deprioritized for this next-family transaction because three of four representative subfamilies expose only NRND exact identities. It is not rejected for future support.

STM32L4 remains eligible. The three non-Active STM32L462 proposal/preview/evaluation variants coexist with Active STM32L462 exact identities, so lifecycle remains an exact-variant property rather than a family-level exclusion.

## 5. Ordering Information gate

Eligible families after lifecycle disposition:

```text
STM32L0
STM32L4
```

Official ST Ordering Information review:

- L0: 16/16 representative targets covered; 16 official datasheets; 0 blocking issues
- L4: 24/24 representative targets covered; 20 official datasheets; 0 blocking issues
- required ordering evidence schema complete for both
- revision drift: false
- evidence quality result: `equivalent_required_ordering_evidence_quality`

Ordering review artifact:

`data/device-catalog/research/stm32-l0-l4-post-c0-ordering-authority-review.json`

## 6. Deterministic selection

Because L0 and L4 both pass manufacturer lifecycle and Ordering Information gates with equivalent required evidence quality, the already-frozen post-C0 shortlist order is the final tie-break.

Result:

`selected_next_research_family = STM32L0`

This is **research selection only**. A future STM32L0 discovery phase requires a new Gate 1.

Frozen artifact:

`data/device-catalog/research/stm32-post-c0-next-family-selection.json`

## 7. Frozen digests

- selection SHA-256: `a46cef39516bf94901b979ccfc446b5720b2c6855b46ede1765232f6082df134`
- authoritative summary SHA-256: `45c3020462601e6cb36e726cc1acc4203abc36a96063a5223ab5c7511bcff02c`
- authoritative provenance SHA-256: `e55b5a94090b36aa4b30b8539cf29c3513bafb3b79d0360031a3ad413f38e34d`
- target manifest SHA-256: `767ad681a7d8e839cbf68b507babb2c417905a2f40a380566e773fa987ab9434`
- Ordering Information review SHA-256: `d16e71cb322c7da754ed12cc1bd0e984015888cbf8bdb07685e1d87966ad8612`
- immutable post-C0 Production prestate SHA-256: `15f9c9a9be8640bc0664b562c667f676d0084e4c157e01f582c87a10886c5420`
- OpenOCD catalog SHA-256 at live acquisition: `43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3`

## 8. Permanent validation

Permanent offline validation covers:

- post-C0 912-row Production prestate binding
- deterministic 44-target boundary
- official-ST source authority
- zero manual-review requirement
- exact identity/lifecycle join integrity
- retained summary/provenance/target digest locks
- all 44 per-target retained JSONs equal their authoritative summary evidence objects
- L1 lifecycle deprioritization
- L4 exact-variant lifecycle semantics
- L0/L4 Ordering Information completeness
- deterministic frozen selection replay
- all support/admission authority boundaries remain false

Permanent workflow:

`.github/workflows/device-catalog-stm32-post-c0-selection-validation.yml`

Temporary live/generator/retention workflows were removed from the final intended diff.

## 9. Next gate

Finish final-head CI, verify `main` has not drifted from `878e0b7b874c5aa45b55ee619e5d30531d2dd037`, confirm no unresolved review threads, then stop for explicit **Gate 2 merge approval** on PR #504.

After merge, Production remains **912 exact ICPNs (delta 0)**. The next possible transaction would be an STM32L0 bounded research/discovery phase, which requires a new Gate 1.
