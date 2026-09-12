# H012 — STM32 Post-C0 Next-Family Evidence Selection Handover

**Date:** 2026-09-12
**Status:** Complete; PR #504 merged
**Primary workstream:** Device Catalog / STM32 next-family research selection
**Repository:** `physicslu/plasma`
**Branch:** `agent/device-catalog-post-c0-evidence-selection`
**PR:** #504
**Merge commit:** `7e2c23bbd6f5ce5f8e9633a0e7178e006767c9c3`

## 1. Starting state

STM32C0 C0.5 was merged as PR #503 at merge commit:

`878e0b7b874c5aa45b55ee619e5d30531d2dd037`

Production was authoritative at 912 exact ICPNs / 293 Base Devices / 10 STM32 families, including 209 STM32C0 exact ICPNs.

The read-only cross-family shortlist after C0 publication was:

1. STM32L1
2. STM32L0
3. STM32L4

## 2. Transaction boundary

Gate 1 authorized a bounded, read-only official-ST manufacturer-evidence accessibility comparison over L1/L0/L4 and selection of the **next research family only**.

The transaction did not add/admit ICPNs, modify Production, define programming policy, prove Flash algorithm/geometry equivalence, qualify option/security or socket/electrical/HIL behavior, or claim PPU/runtime programming support.

## 3. Deterministic representative surface

One lexical-min Base Device was selected per guarded OpenOCD ordering-pattern subfamily:

```text
STM32L1:  4
STM32L0: 16
STM32L4: 24
Total:   44
```

OpenOCD bounded research only; it was not commercial identity/lifecycle authority.

## 4. Authoritative live acquisition

Official ST dual-surface acquisition completed successfully:

- workflow run: `34674798156`
- targets/dispositioned: 44/44
- manual review: 0
- artifact ZIP SHA-256: `b179c6429e095b5407ddfa44779f3cbf3e84930b4f6e00d0e4bfb4027016a6c2`

Observed result:

```text
L1: 4 targets / 1 Active / 3 lifecycle-excluded / 1 Active exact / 8 non-Active exact
L0: 16 targets / 16 Active / 0 lifecycle-excluded / 44 Active exact
L4: 24 targets / 24 Active / 0 lifecycle-excluded / 60 Active exact / 3 extra non-Active exact
```

STM32L1 was deprioritized for this transaction because three of four representatives exposed only NRND identities. STM32L4 remained eligible because its non-Active variants coexist with Active exact identities.

## 5. Ordering Information gate

Official ST Ordering Information review found:

- L0: 16/16 representatives covered by 16 official datasheets; 0 blocking issues
- L4: 24/24 representatives covered by 20 official datasheets; 0 blocking issues
- evidence result: `equivalent_required_ordering_evidence_quality`

## 6. Deterministic selection

Because L0 and L4 passed manufacturer lifecycle and Ordering Information gates with equivalent required evidence quality, the already-frozen post-C0 shortlist order was the final tie-break.

`selected_next_research_family = STM32L0`

This was research selection only.

## 7. Frozen digests

- selection: `a46cef39516bf94901b979ccfc446b5720b2c6855b46ede1765232f6082df134`
- authoritative summary: `45c3020462601e6cb36e726cc1acc4203abc36a96063a5223ab5c7511bcff02c`
- authoritative provenance: `e55b5a94090b36aa4b30b8539cf29c3513bafb3b79d0360031a3ad413f38e34d`
- target manifest: `767ad681a7d8e839cbf68b507babb2c417905a2f40a380566e773fa987ab9434`
- Ordering review: `d16e71cb322c7da754ed12cc1bd0e984015888cbf8bdb07685e1d87966ad8612`
- immutable post-C0 Production prestate: `15f9c9a9be8640bc0664b562c667f676d0084e4c157e01f582c87a10886c5420`
- OpenOCD catalog: `43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3`

## 8. Completion

PR #504 was synchronized to the then-current `main`, requalified with all applicable CI successful, and merged at:

`7e2c23bbd6f5ce5f8e9633a0e7178e006767c9c3`

Production remained **912 exact ICPNs (delta 0)**.

## 9. Continuation

Current STM32 Device Catalog continuation moved to **H013 — STM32L0 L0.1 Foundation**.
