# Plasma IC Support — Phase A Pilot

`data/ic-support/` owns the technical knowledge required to answer:

> How does Plasma support this IC?

It does **not** own commercial IC identity. Exact ICPN, manufacturer, family, package and current catalog admission remain owned by `data/device-catalog/`.

## Phase A boundary

This directory is a research/pilot contract. It does not change the Programming runtime, does not make a support claim, and cannot create PPU/Socket/real-IC validation evidence.

```text
Device Catalog (Who is this IC?)
        |
        | exact ICPN
        v
IC Support binding
        |
        +-- Programming Profile
        +-- Memory Geometry Profile
        +-- Package / Minimum Hardware Profile
        +-- Option Profile
        +-- Security Profile
        `-- Revision Overrides
```

The Phase A target is `STM32F103C8T6` + `STM32F103CBT6`. The pair is deliberately chosen to test profile reuse: they share the programming behavior under test while their Flash geometries differ.

## Layout

```text
data/ic-support/
├── schema/
├── evidence/
│   ├── sources.json
│   └── source_integrity.py
├── evidence-pack/
│   ├── schema/
│   ├── fixtures/
│   ├── policies/
│   ├── contract.py
│   ├── preprocessing.py
│   ├── semantic_pack.py
│   ├── normalization-v0.json
│   ├── taxonomy-v0.json
│   └── rules-v0.json
├── profiles/
│   ├── programming/
│   ├── memory-geometry/
│   ├── package-hardware/
│   ├── option/
│   ├── security/
│   └── revision/          # reserved for future artifacts; overrides live on bindings
├── bindings/
└── benchmarks/
    └── stm32f103c/
        ├── source-lock.json
        ├── extraction-contract.json
        ├── evidence-pack-benchmark-v0.json
        ├── ground-truth.json
        └── generated/
```

Empty directories are not Git artifacts; `revision/` is a conceptual slot only until a real revision-specific record exists.

## Evidence rule

Every technical profile must cite evidence. Evidence now has five separate responsibilities:

1. `evidence/sources.json` is the logical source catalog: document identity, revision, authority and retrieval location.
2. `benchmarks/stm32f103c/source-lock.json` is the immutable benchmark lock: exact source IDs plus content digests/byte lengths used to establish the answer key.
3. `evidence-pack/preprocessing.py` deterministically converts one exact source-locked PDF into a structural manifest with physical-page preservation, preprocessing/normalization fingerprints, structural candidates and explicit-reference candidates. It does not perform semantic evidence classification.
4. `evidence-pack/semantic_pack.py` resolves an admitted deterministic semantic policy against that manifest, builds page-atomic Evidence Units, applies mandatory seeds and dependency closure, and creates an Evidence Pack plus applicability/bundle artifacts.
5. `evidence-pack/contract.py` defines reusable Evidence Unit Catalog, Evidence Pack, evidence-backed Applicability Binding and per-target Evidence Bundle contracts and trust boundaries.

Evidence Packs do not replace source locks and do not grant IC Support or production admission. A document may be shared by many ICPNs; the pack is document/purpose scoped and reusable rather than duplicated per part number. Exact ICPNs resolve packs through evidence-backed applicability claims.

For the STM32F103C benchmark, ST `DS5319 Rev 20` and `PM0075 Rev 2` are SHA-256 pinned from bytes downloaded from official ST URLs. The retained Plasma STM32F1 commercial catalog is pinned by exact Git blob SHA.

The external PDFs are not redistributed in Git. Reproducibility is provided by the source lock plus `source_integrity.py verify`, which downloads the official URLs and fails if the bytes no longer match the lock. Evidence processing retains policy, structural metadata, recipes and digests rather than manufacturer body text.

Document preprocessing fingerprints the exact `pdftotext` version and arguments, the versioned normalization contract and the preprocessing implementation bytes. Every physical PDF page must survive as exactly one `PAGE` unit even if structural heading detection fails. Section/table/figure detection remains candidate metadata.

The DS5319 semantic policy uses exact section labels plus heading regexes and must resolve each admitted rule uniquely. Table-of-contents aliases or ambiguous structural targets cannot silently satisfy a rule. Physical pages are the v0 atomic semantic Evidence Units; dependency closure may pull an otherwise excluded page back into the pack when a deterministic explicit reference uniquely resolves.

No missing technical field may be filled by family-name inference. `pending_evidence` is valid; invented detail is not. Evidence Pack applicability follows the same rule: manufacturer scope expressions require included evidence and an unbound exact ICPN fails closed.

## Benchmark isolation

A real Harness/AI benchmark run must be isolated from the answer key. `benchmarks/stm32f103c/extraction-contract.json` defines the allowed source IDs and explicitly forbids reading:

- `ground-truth.json`;
- checked-in IC Support profiles;
- checked-in bindings.

The candidate must report the exact source digests it consumed. A result generated from a different source revision or after reading the answer key is not a valid benchmark sample.

The manufacturer-only Evidence Pack A/B experiment is deliberately separate from the formal blind benchmark. `evidence-pack-benchmark-v0.json` is now a runnable contract comparing full DS5319 + full PM0075 against deterministic DS5319 Evidence Pack + full PM0075 while keeping the existing formal three-source lock unchanged.

Actual manufacturer-content-derived pack outputs are generated outside Git. `.github/workflows/ic-evidence-live-validation.yml` separately verifies the exact DS5319 source and semantic policy against the real PDF while retaining only metadata/digests as an artifact; ordinary deterministic IC Support CI remains independent of ST availability.

## Validation

Run the deterministic/offline checks from the repository root:

```bash
python data/ic-support/validate.py
python data/ic-support/evidence-pack/validate_contract.py
python data/ic-support/evidence-pack/validate_preprocessing.py
python data/ic-support/evidence-pack/validate_semantic_pack.py
python data/ic-support/benchmarks/stm32f103c/validate_source_lock.py
python data/ic-support/compare_benchmark.py
python data/ic-support/test_ic_support.py
python data/ic-support/benchmarks/stm32f103c/test_extraction_contract.py
```

`validate.py` cross-checks each pilot ICPN against the existing STM32F1 commercial catalog, resolves every profile reference, validates evidence references, verifies geometry arithmetic, and enforces the intended C8/CB reuse boundary.

`evidence-pack/validate_contract.py` validates the Evidence Pack foundation: exact source-lock fingerprint binding, reproducibility identities, mandatory/unknown fail-closed behavior, dependency closure, AI add-only enrichment, many-to-many pack reuse, applicability evidence and denial of canonical/production admission.

`evidence-pack/validate_preprocessing.py` validates deterministic preprocessing invariants using synthetic content only: newline/whitespace normalization, physical-page preservation, structural-candidate isolation, ambiguous-reference refusal, source-lock drift rejection, manifest mutation detection and identity sensitivity to tool/normalization/builder changes.

`evidence-pack/validate_semantic_pack.py` validates the DS5319 deterministic semantic policy, page reduction, TOC-decoy rejection, C8/CB pack reuse, policy/source-lock drift rejection, explicit dependency closure and reduced-context materialization using metadata/synthetic content only.

`validate_source_lock.py` proves that the answer key, extraction contract and locked evidence set agree and that the retained catalog Git blob has not drifted.

`compare_benchmark.py` compares the normalized observed projection with the source-locked ground truth. `validate_extraction_candidate.py` additionally enforces benchmark/source-lock metadata before accepting a Harness/AI candidate.

The general networked source-byte verification remains separate from deterministic CI:

```bash
python data/ic-support/evidence/source_integrity.py verify
```

## Explicit non-goals

- no AI/LLM semantic classifier or generic RAG implementation in the deterministic Evidence Pack path;
- no AI authority to exclude evidence or create authoritative dependency edges;
- no runtime `ResolvedICSupport` change from this workstream;
- no changes to `SiteManager`, Handler or OpenOCD execution;
- no PMode/EMode behavior change;
- no claim that Mock/CI means real IC support;
- no OTP/eFuse capability claim;
- no silicon-revision override without explicit errata/revision evidence;
- no migration of the existing Device Catalog;
- no claim that the current session is a valid blind AI extraction run.
