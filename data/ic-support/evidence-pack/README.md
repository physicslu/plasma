# IC Evidence Pack Contract Foundation

Status: research contract foundation

This directory defines the deterministic contract between locked manufacturer documents and AI-assisted IC knowledge extraction. It does not admit an IC for production programming, does not replace Device Catalog retained evidence, and does not make AI output authoritative.

## Responsibility boundary

```text
Source Lock
    -> Deterministic Document Preprocessing
    -> Document Structure Manifest
    -> Deterministic Semantic Policy
    -> Evidence Unit Catalog
    -> Mandatory Seed Selection
    -> Dependency Closure
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
4. Semantic policy resolution is deterministic. Admitted rules use exact structural labels plus heading regular expressions and fail closed unless they resolve uniquely.
5. The v0 semantic catalog uses physical pages as atomic Evidence Units. Section/table/figure metadata selects and classifies pages but does not replace page provenance.
6. Evidence Packs reference Evidence Units; they do not duplicate manufacturer document content in Git.
7. One Evidence Pack may apply to many exact ICPNs, and one ICPN may consume many Evidence Packs.
8. Applicability is itself an evidence-backed claim. Family-name similarity is not authority.
9. The same Evidence Pack may support different target-specific canonical values when the underlying manufacturer table contains multiple device variants.
10. `UNKNOWN` classification fails closed into inclusion for v0.
11. Dependency closure outranks ordinary exclusion rules. Only uniquely resolved deterministic/document-explicit references gain authoritative closure; ambiguous references do not.
12. Optional AI/RAG enrichment may add supplemental Evidence Units but must never remove deterministic Evidence Units.
13. Document applicability does not imply canonical-spec admission, runtime support, HIL success, or production admission.
14. Source, preprocessing, semantic-policy, taxonomy, rule, normalization, and builder fingerprints participate in reproducibility identity.

## Git and manufacturer-content policy

The repository stores contracts, recipes, digests, structural metadata, semantic policy, synthetic fixtures, and tests. Original manufacturer PDFs and generated large extracted-text payloads remain outside Git and are reconstructed from source locks/caches. Actual `structure.json`, `catalog.json`, `pack.json`, `binding.json`, target bundles, and `evidence.txt` are generated from the exact locked source in an external workspace. Manufacturer page text is not committed to Git.

## DS5319 Rev 20 semantic Evidence Pack

`policies/st-ds5319-rev20-programming-v0.json` is the first admitted deterministic semantic policy. It is locked to `st_ds5319_rev20` and the exact SHA-256/byte length in the STM32F103C source lock. The policy classifies programming-relevant device identity, ordering, memory-map, Flash, debug, boot, reset, clock, power, security, relevant electrical, and pin evidence while treating document navigation, unrelated peripheral material, package-mechanical material, and other electrical material as omit-by-default.

The broad exclusions are not deletion authority. A uniquely resolved explicit dependency from an included page can pull an otherwise excluded page into the final pack. `UNKNOWN` remains fail-closed include.

C8 and CB reuse the same DS5319 pack through separate evidence-backed applicability claims. Sharing the pack does not imply that target-specific canonical values such as Flash geometry are identical.

Generate the actual source-derived artifacts outside the repository:

```bash
python data/ic-support/evidence-pack/semantic_pack.py \
  --source-lock data/ic-support/benchmarks/stm32f103c/source-lock.json \
  --policy data/ic-support/evidence-pack/policies/st-ds5319-rev20-programming-v0.json \
  --pdf /outside/repo/st_ds5319_rev20.pdf \
  --output-dir /outside/repo/ds5319-pack
```

The command first verifies the locked PDF, records the actual `pdftotext` fingerprint, preprocesses all physical pages, resolves the semantic policy, applies mandatory seed rules and dependency closure, builds C8/CB applicability/bundles, and materializes `evidence.txt` for the reduced-context benchmark arm.

## Live-source validation

`.github/workflows/ic-evidence-live-validation.yml` is intentionally separate from deterministic repository CI. It downloads the official DS5319 URL, verifies the exact locked SHA-256 and byte length, builds the real Evidence Pack, and uploads only a metadata/digest report. Manufacturer page text is not uploaded as an artifact.

An external ST outage can make live-source validation unavailable; it must not be confused with a deterministic code regression. Conversely, a successful synthetic test is not sufficient evidence that the real PDF policy resolves: the live-source run is the real-source acceptance signal.

## v0 artifacts

- `schema/evidence-pack-v0.schema.json`: structural contract for Evidence Unit catalogs, packs, applicability bindings, and target bundles.
- `schema/document-structure-v0.schema.json`: deterministic structural-manifest contract produced before semantic classification.
- `schema/semantic-policy-v0.schema.json`: deterministic semantic policy contract.
- `normalization-v0.json`: versioned extracted-text normalization contract.
- `preprocessing.py`: source-lock verification, `pdftotext` fingerprinting, normalization, page preservation, structural candidate generation and manifest validation.
- `semantic_pack.py`: semantic policy resolution, page catalog construction, dependency closure input generation, Evidence Pack/binding/bundle construction, and evidence-text materialization.
- `policies/st-ds5319-rev20-programming-v0.json`: DS5319 Rev 20 programming-evidence semantic policy.
- `PREPROCESSING.md`: preprocessing trust boundary, reproducibility model and CLI usage.
- `taxonomy-v0.json`: semantic categories only; inclusion policy is intentionally separate.
- `rules-v0.json`: deterministic inclusion/exclusion policy and precedence.
- `contract.py`: Evidence Pack identity, resolution, dependency-closure, and fail-closed logic.
- `fixtures/stm32f103c-foundation-v0.json`: synthetic metadata fixture representing the DS5319/PM0075 reuse shape without embedding manufacturer text.
- `fixtures/synthetic-document-v0.json`: synthetic extracted-text fixture for preprocessing invariants.
- `fixtures/st-ds5319-rev20-outline-v0.json`: retained structural outline used to regression-test the DS5319 policy without redistributing manufacturer body text.
- `test_contract.py`, `test_preprocessing.py`, `test_semantic_pack.py`: deterministic contract tests.

## Validation

```bash
python data/ic-support/evidence-pack/validate_contract.py
python data/ic-support/evidence-pack/validate_preprocessing.py
python data/ic-support/evidence-pack/validate_semantic_pack.py
```

The existing `data/ic-support/benchmarks/stm32f103c/source-lock.json` remains the source-byte authority for the STM32F103C formal blind benchmark. The manufacturer-only Full-vs-Pack experiment is separate and does not redefine that three-source benchmark.
