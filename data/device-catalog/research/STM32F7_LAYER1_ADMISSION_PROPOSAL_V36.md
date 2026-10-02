# STM32F7 Layer-1 Catalog Admission Proposal v3.6

**Research proposal only. Production publication requires explicit owner approval.**

## Proposed transaction

The merged v3.4 exact-gap lock and v3.5 metadata replay establish **154/154** missing current-Active STM32F7 exact MPNs as metadata-ready.

If explicitly approved for Production publication:

- add **154** normalized STM32F7 exact identities;
- F7 current Active identity coverage becomes **173/173 = 100%**;
- Production exact total would move **4,088 → 4,242**;
- whole-ST current Active intersection would move **4,009 → 4,163**;
- whole-ST Active gap would move **541 → 387**;
- whole-ST Active identity coverage would move **88.1099% → 91.4945%**.

## Catalog-only backend boundary

Backend capability is not evaluated in this workstream.

All 154 proposed rows use `no_mapping` as the safe Catalog/runtime state: **no route is bound**. This is not a claim that a suitable OpenOCD route is absent.

No Programming Profile applicability, Engineering Verified status, field evidence, or HIL claim is introduced.

## Metadata authority

- **151** rows decode directly from official ST Ordering Information.
- **3** STM32F750 x8 rows use exact-product-bounded official ST metadata:
  - `STM32F750V8T6`
  - `STM32F750V8T7`
  - `STM32F750Z8T6`

The override does not authorize a generalized STM32F750 x8 decoder.

## Review artifact

CI generates the complete 154-row proposal CSV and machine-readable summary. Their exact-set, CSV and authority SHA-256 values are frozen into this PR before merge.

No canonical Production Catalog file is modified by this proposal.
