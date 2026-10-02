# STM32F3 Layer-1 Catalog Admission Proposal v3.2

**Research proposal only. Production publication requires explicit owner approval.**

## Proposed Layer-1 transaction

The locked v3.0 gap and v3.1 metadata replay establish **182/182** missing current-Active STM32F3 exact MPNs as metadata-ready, with no metadata exceptions.

If explicitly approved for Production publication:

- add **182** normalized STM32F3 exact identities;
- F3 current Active identity coverage becomes **192/192 = 100%**;
- Production exact total would move **3,906 → 4,088**;
- whole-ST current Active intersection would move **3,827 → 4,009**;
- whole-ST Active gap would move **723 → 541**;
- whole-ST Active identity coverage would move **84.1099% → 88.1099%**.

## Catalog-only backend boundary

Backend capability is **not evaluated** in this workstream.

For safe Catalog/runtime representation, all 182 new rows are proposed with `no_mapping`: this means **no route is bound**, not that a suitable backend route has been proven absent.

No OpenOCD target, Programming Profile applicability, Engineering Verified status, field evidence, or HIL claim is introduced.

## Metadata authority

The proposal is generated from the v3.1 series/density-band-specific ST Ordering Information authority. F302/F303 density bands remain separately governed and package-dependent physical pin counts remain fail-closed.

## Review artifact

CI generates:

- complete 182-row proposal CSV;
- machine-readable proposal summary;
- deterministic exact-set, proposal CSV and authority SHA-256 locks.

No canonical Production Catalog source is modified by this PR.
