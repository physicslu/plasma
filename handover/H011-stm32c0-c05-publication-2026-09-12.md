# H011 — STM32C0 C0.5 Controlled Publication Handover

**Date:** 2026-09-12
**Status:** C0.5 implementation complete on feature branch; Gate 2 pending
**Primary workstream:** Device Catalog / STM32C0
**Repository:** `physicslu/plasma`
**Branch:** `agent/device-catalog-stm32c0-phase-c05-publication`

## 1. Transaction boundary

C0.5 publishes exactly the 209 exact STM32C0 ICPNs admitted by C0.4 into the canonical Device Catalog and Production manifest.

The full closed commercial surface remains 220 manufacturer-verified Active / 220 metadata-ready exact ICPNs. Eleven identities remain capability-unresolved and are excluded from Production; they are not identity rejects.

C0.5 does not establish Flash algorithm/geometry equivalence, option/security semantics, physical/HIL qualification, electrical/socket support, or PPU/runtime programming support.

## 2. Deterministic closure

```text
manufacturer-verified:       220
metadata-ready:              220
C0.4 capability-admittable:  209
C0.5 published exact ICPNs:  209
published Base Devices:       50
capability-unresolved:        11
identity rejects:              0
```

Production state on the C0.5 branch:

```text
before: 703 exact / 243 Base Devices / 9 families / STM32C0 0
after:  912 exact / 293 Base Devices / 10 families / STM32C0 209
```

Main remains at the pre-publication state until Gate 2 merge.

## 3. Frozen digests

- C0.4 admission-plan SHA-256: `36db8e0c34fdbaf46a2ee6dc8df5a09171f6a4434572f9b2cf49cabf63361056`
- prestate Production SHA-256: `903476d41997f9d20c237bccea0ee1e085fc343730e0d3740b2b82b0de0462b0`
- prestate Production Git blob: `89cbaa8807daf8f9c55bc8c1ca0bc1c05eaec1fc`
- canonical STM32C0 SHA-256: `d473c7a1b3b72b75314732ffd59bf8a8b0a39eaf8d632ba935e9e1b71509f96b`
- canonical STM32C0 Git blob: `0bf125dd071312cf31c57cfa7ebe3b29ffdda845`
- publication proposal SHA-256: `af207b92efc84d37c04755d0512b521392185f26c4b971f52ed6a7fb9644cf9f`
- publication audit SHA-256: `b351bb5b1a27c62899b23473001caacc4e8a42e4f2395051ad68468d547e9953`
- poststate Production SHA-256: `15f9c9a9be8640bc0664b562c667f676d0084e4c157e01f582c87a10886c5420`
- poststate Production Git blob: `8abfcc870e51ac4232cdf8d807828cfe4ff5662d`
- unresolved exact-set SHA-256: `32698be0aee4f95360a1b27ddfecd1034d7627e0b223dd8873153b5d96ec5601`

## 4. Unresolved exact ICPNs

`STM32C051K8U3`, `STM32C051K8U3TR`, `STM32C051K8U6`, `STM32C051K8U6TR`, `STM32C051K8U7`, `STM32C051K8U7TR`, `STM32C071FBY6TR`, `STM32C071R8I6N`, `STM32C071RBI6N`, `STM32C091RBI6`, `STM32C092RBI6`.

They remain manufacturer-verified and metadata-ready. A future routing-evidence transaction is required before any of them can be admitted.

## 5. Implemented assets

- `data/device-catalog/research/stm32c0-commercial-icpn.csv`
- `data/device-catalog/research/stm32c0-phase-c0.5-publication-proposal.json`
- `data/device-catalog/research/stm32c0-phase-c0.5-publication-audit.json`
- `data/device-catalog/research/publish_stm32c0_phase_c0_5.py`
- `data/device-catalog/research/test_stm32c0_phase_c0_5_publication.py`
- `data/device-catalog/research/device-catalog-stm32c0-phase-c0.5-publication.md`
- `data/device-catalog/research/stm32c0-phase-c0.2-production-manifest-prestate.json`
- `.github/workflows/device-catalog-stm32c0-c05-publication-validation.yml`
- Production manifest adds exactly one STM32C0 source with 209 rows.

Historical replay boundaries were corrected so C0.2/C0.3/C0.4 validate against immutable historical prestates rather than mutable live Production. C0.4 retains an explicit live-manifest helper for negative tests, while its default replay canonical prestate remains absent.

## 6. Focused validation

A branch-side deterministic generation transaction produced the committed bytes and measured the exact poststate. A complete focused lifecycle validation subsequently passed:

- C0.2 retained evidence validator — PASS
- C0.3 policy tests — 15 PASS
- C0.4 admission tests — 14 PASS
- C0.4 frozen-plan validator — VALID
- C0.5 publication tests — 8 PASS
- C0.5 publisher `--verify` — VALID
- current cross-family prioritization — PASS
- historical post-U0 evidence probe — PASS
- centralized family-CI self-test — PASS

Final PR CI and `main` drift still require verification before Gate 2.

## 7. Current cross-family consequence

With STM32C0 published, the current read-only research shortlist is now:

1. STM32L1
2. STM32L0
3. STM32L4

This is selection state only. It does not authorize a new family transaction.

## 8. Next gate

After temporary generator/repair workflows are removed, repository documentation is finalized, PR CI is green, and `main` is synchronized, C0.5 must stop at **Gate 2 — explicit merge approval**.
