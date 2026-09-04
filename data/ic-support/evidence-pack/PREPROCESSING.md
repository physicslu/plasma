# Deterministic Document Preprocessing

This layer converts exact source-locked manufacturer PDFs into reproducible structural metadata. It intentionally stops before semantic evidence classification.

```text
Locked PDF bytes
  -> verify source-lock SHA-256 / byte length
  -> pdftotext -layout -enc UTF-8
  -> versioned text normalization
  -> physical page recovery
  -> PAGE units + structural candidates
  -> explicit-reference candidates
  -> Document Structure Manifest
```

## Trust boundary

- Every physical PDF page becomes exactly one `PAGE` unit. Heading detection failure must not drop evidence.
- `SECTION_CANDIDATE`, `TABLE_CANDIDATE`, and `FIGURE_CANDIDATE` are structural hints only. They are not taxonomy classifications.
- Explicit references such as `See Table 3` remain `DOCUMENT_EXPLICIT_CANDIDATE`. A unique label match resolves a structural target but does not itself become an authoritative Evidence Pack dependency edge.
- Ambiguous and missing references remain unresolved rather than guessed.
- `printed_page_label` is nullable in v0; zero-based `pdf_page_index` is the authoritative physical page coordinate.
- Manufacturer text payloads are not committed to Git. The manifest contains structural metadata and content digests.
- Structural manifests explicitly deny semantic-classification, canonical-dataset, and production admission.

## Reproducibility identity

A manifest changes when any of the following changes:

```text
source bytes / source-lock fingerprint
pdftotext version
pdftotext arguments
normalization contract
preprocessing implementation bytes
normalized page content / structural metadata
```

The runtime builder fingerprints its own `preprocessing.py` bytes and records the exact first line returned by `pdftotext -v` under `LC_ALL=C` / `LANG=C`.

## Usage

The original PDF must already have been materialized from the source lock or an integrity-verified cache:

```bash
python data/ic-support/evidence-pack/preprocessing.py \
  --source-lock data/ic-support/benchmarks/stm32f103c/source-lock.json \
  --source-id st_ds5319_rev20 \
  --pdf /outside/repo/st_ds5319_rev20.pdf \
  --output /outside/repo/st_ds5319_rev20.structure.json
```

The output should remain outside the repository when it is generated from manufacturer content. Git stores the schema, normalization contract, builder and synthetic tests required to reproduce it.

## Validation

```bash
python data/ic-support/evidence-pack/validate_preprocessing.py
```

The deterministic CI suite uses synthetic extracted text and does not require network access or manufacturer PDFs. Real locked-PDF preprocessing is an evidence-generation operation and must first verify the source lock.
