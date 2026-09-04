# IC Evidence Pack Contract Foundation

Status: research contract foundation

This directory defines the deterministic contract between locked manufacturer documents and AI-assisted IC knowledge extraction. It does not admit an IC for production programming, does not replace Device Catalog retained evidence, and does not make AI output authoritative.

## Responsibility boundary

```text
Source Lock
    -> Deterministic Document Preprocessing
    -> Document Structure Manifest
    -> Evidence Unit Catalog
    -> Evidence Pack
    -> Applicability Binding
    -> Target Evidence Bundle
    -> IC Knowledge Agent
    -> Candidate Canonical Specification
    -> deterministic semantic validation
```

The evidence-governance artifacts before the IC Knowledge Agent remain separate from canonical semantic validation.

## Core rules

1. A source document is preprocessed once per exact source digest + preprocessor fingerprint + normalization contract + builder implementation.
2. Every physical PDF page survives preprocessing as exactly one `PAGE` structural unit, even when heading detection fails.
3. Structural headings/tables/figures are candidates only; preprocessing does not assign semantic taxonomy categories.
4. Evidence Packs reference Evidence Units; they do not duplicate manufacturer document content.
5. One Evidence Pack may apply to many exact ICPNs, and one ICPN may consume many Evidence Packs.
6. Applicability is itself an evidence-backed claim. Family-name similarity is not authority.
7. The same Evidence Pack may support different target-specific canonical values when the underlying manufacturer table contains multiple device variants.
8. `UNKNOWN` classification fails closed into inclusion for v0.
9. Dependency closure outranks ordinary exclusion rules.
10. Optional AI/RAG enrichment may add supplemental Evidence Units but must never remove deterministic Evidence Units.
11. Document applicability does not imply canonical-spec admission, runtime support, HIL success, or production admission.
12. Source, preprocessing, taxonomy, rule, and normalization fingerprints all participate in reproducibility identity.

## Git and manufacturer-content policy

The repository stores contracts, recipes, digests, unit metadata, synthetic fixtures, and tests. Original manufacturer PDFs and generated large extracted-text payloads remain outside Git and are reconstructed from source locks/caches. Structural manifests and Evidence Unit metadata contain content digests rather than redistributing manufacturer text.

## v0 artifacts

- `schema/evidence-pack-v0.schema.json`: structural contract for Evidence Unit catalogs, packs, applicability bindings, and target bundles.
- `schema/document-structure-v0.schema.json`: deterministic structural-manifest contract produced before semantic classification.
- `normalization-v0.json`: versioned extracted-text normalization contract.
- `preprocessing.py`: source-lock verification, `pdftotext` fingerprinting, normalization, page preservation, structural candidate generation and manifest validation.
- `PREPROCESSING.md`: preprocessing trust boundary, reproducibility model and CLI usage.
- `taxonomy-v0.json`: semantic categories only; inclusion policy is intentionally separate.
- `rules-v0.json`: deterministic inclusion/exclusion policy and precedence.
- `contract.py`: Evidence Pack identity, resolution, dependency-closure, and fail-closed logic.
- `fixtures/stm32f103c-foundation-v0.json`: synthetic metadata fixture representing the DS5319/PM0075 reuse shape without embedding manufacturer text.
- `fixtures/synthetic-document-v0.json`: synthetic extracted-text fixture for preprocessing invariants.
- `test_contract.py` / `test_preprocessing.py`: deterministic contract tests.

The existing `data/ic-support/benchmarks/stm32f103c/source-lock.json` remains the source-byte authority for the STM32F103C benchmark. This foundation does not redefine that formal blind benchmark.
