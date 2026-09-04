# IC Evidence Pack Contract Foundation

Status: research contract foundation

This directory defines the deterministic contract between locked manufacturer documents and AI-assisted IC knowledge extraction. It does not admit an IC for production programming, does not replace Device Catalog retained evidence, and does not make AI output authoritative.

## Responsibility boundary

```text
Source Lock
    -> Evidence Unit Catalog
    -> Evidence Pack
    -> Applicability Binding
    -> Target Evidence Bundle
    -> IC Knowledge Agent
    -> Candidate Canonical Specification
    -> deterministic semantic validation
```

The first five artifacts are evidence-governance artifacts. Canonical semantic validation is a separate downstream trust boundary.

## Core rules

1. A source document is preprocessed once per exact source digest + preprocessor fingerprint + normalization contract.
2. Evidence Packs reference Evidence Units; they do not duplicate manufacturer document content.
3. One Evidence Pack may apply to many exact ICPNs, and one ICPN may consume many Evidence Packs.
4. Applicability is itself an evidence-backed claim. Family-name similarity is not authority.
5. The same Evidence Pack may support different target-specific canonical values when the underlying manufacturer table contains multiple device variants.
6. `UNKNOWN` classification fails closed into inclusion for v0.
7. Dependency closure outranks ordinary exclusion rules.
8. Optional AI/RAG enrichment may add supplemental Evidence Units but must never remove deterministic Evidence Units.
9. Document applicability does not imply canonical-spec admission, runtime support, HIL success, or production admission.
10. Source, preprocessing, taxonomy, rule, and normalization fingerprints all participate in reproducibility identity.

## Git and manufacturer-content policy

The repository stores contracts, recipes, digests, unit metadata, synthetic fixtures, and tests. Original manufacturer PDFs and generated large extracted-text payloads remain outside Git and are reconstructed from source locks/caches. Evidence Unit metadata contains content digests rather than redistributing manufacturer text.

## v0 artifacts

- `schema/evidence-pack-v0.schema.json`: structural contract for Evidence Unit catalogs, packs, applicability bindings, and target bundles.
- `taxonomy-v0.json`: semantic categories only; inclusion policy is intentionally separate.
- `rules-v0.json`: deterministic inclusion/exclusion policy and precedence.
- `contract.py`: identity, resolution, dependency-closure, and fail-closed logic.
- `fixtures/stm32f103c-foundation-v0.json`: synthetic metadata fixture representing the DS5319/PM0075 reuse shape without embedding manufacturer text.
- `test_contract.py`: deterministic contract tests.

The existing `data/ic-support/benchmarks/stm32f103c/source-lock.json` remains the source-byte authority for the STM32F103C benchmark. This foundation does not redefine that formal blind benchmark.
