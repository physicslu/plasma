# NXP KL25 Gate 5.8 — Manufacturer Evidence Semantic + Citation Review

Target: `MKL25Z128VLK4`

## Objective

Gate 5.8 converts the successful Gate 5.7A `READY_FOR_REVIEW` result into an explicit manufacturer-evidence review process. It does **not** generate another model answer.

The exact retained Gate 5.7A run is:

```text
/storage/projects/plasma-benchmark/nxp-kl25/bounded-primary-runs/20260909T080946Z
```

Frozen identity:

```text
target          = MKL25Z128VLK4
contract        = nxp-kl25-live-bounded-qualification-v1.1
execution_mode  = live_bounded_primary_scoped_sequential
bundle_digest   = ffe9bfaa8a6ed47c8edd6d952fe1ca2cc114513c2a1f0832892ab9484e7322bf
manifest_digest = 03155ede421cddb7c2ab64e079ef43b1124a7c78cbedf1e7a08c60c29796bb6e
model           = qwen3.8:27b-mlx
model_digest    = 5642e97495e1a088883805981563dcdc4a040c2f53388b7a41d1f24d3622cf7e
Gate 5.7A       = 8/8, INTEGRITY_PASS, READY_FOR_REVIEW
```

The review question is narrower and stronger than deterministic screening:

> For every retained model fact, does the cited locked NXP manufacturer evidence actually support the statement at the claimed level of specificity?

## Why a new Gate is required

Gate 5.7A proves representation, provenance, allowed citation membership, primary-scope citation presence, model/runtime identity and deterministic screening. Those checks cannot prove natural-language entailment.

A fact can still be wrong even when:

- it is valid JSON;
- its page citation belongs to the admitted Evidence Pack;
- at least one cited page is PRIMARY;
- required NXP terms are present;
- forbidden STM32 terms are absent.

Therefore `READY_FOR_REVIEW` must not be treated as semantic truth.

## Gate 5.8 contract

Repository contract:

```text
gate58-manufacturer-review-contract.json
contract_id = nxp-kl25-gate58-manufacturer-review-v1
```

The contract binds Gate 5.8 to the exact retained run identity above. A different run ID, model digest, bundle, manifest, Gate 5.7A contract or execution mode fails closed.

Gate 5.8 never mutates the retained model output. Every review verdict binds to a deterministic digest of the original fact content.

## Per-fact review dimensions

Each retained fact is reviewed independently across five dimensions.

### Semantic support

```text
NOT_REVIEWED
SUPPORTED                <- PASS
CONTRADICTED
NOT_ESTABLISHED
AMBIGUOUS
```

### Citation entailment

```text
NOT_REVIEWED
COMPLETE                 <- PASS
PARTIAL
NOT_ENTAILED
PADDING_PRESENT
```

`COMPLETE` means the fact-local citation set supports every material clause. It is stronger than merely finding supporting text somewhere else in the Evidence Pack.

### Atomicity

```text
NOT_REVIEWED
PASS                     <- PASS
NEEDS_SPLIT
```

A compound statement that joins materially independent claims with different evidence bases should be rejected for later correction rather than silently rewritten inside the retained run.

### Scope

```text
NOT_REVIEWED
PASS                     <- PASS
OVER_BROAD
PRIMARY_SCOPE_VIOLATION
FORBIDDEN_ASSERTION
```

PRIMARY pages remain semantic fact authority. Dependency pages are supporting context only.

### Terminology

```text
NOT_REVIEWED
PASS                     <- PASS
LOSSY_NXP_TRANSLATION
CROSS_VENDOR_CONTAMINATION
```

NXP-native concepts such as `FTFA`, `FSTAT`, `FCCOB`, `FSEC`, `SWD` and `MDM-AP` must not be replaced by misleading STM32-derived ontology.

## Deterministic review view

`gate58_review.py build-view` consumes the retained Gate 5.7A artifacts and produces a review view containing, for every fact:

```text
primary_unit_id
fact_id
fact_digest
kind
statement
PRIMARY citations
supplemental/dependency citations
all citations
```

The view also carries the exact aggregate, provenance and Gate 5.7A qualification-report digests.

Example command on SWPC:

```bash
python3 data/ic-support/benchmarks/nxp-kl25/gate58_review.py build-view \
  --run-dir /storage/projects/plasma-benchmark/nxp-kl25/bounded-primary-runs/20260909T080946Z \
  --output /storage/projects/plasma-benchmark/nxp-kl25/gate58/review-view.json \
  --template-output /storage/projects/plasma-benchmark/nxp-kl25/gate58/review-verdict.json
```

Output files are created with exclusive-create semantics. Existing review artifacts are not overwritten.

## Review template and qualification

The generated template contains one verdict row for every retained fact. All dimensions initially use `NOT_REVIEWED`, so its deterministic status is `REVIEW_INCOMPLETE`.

The reviewer compares each statement with the locked NXP manufacturer pages and records explicit outcomes plus a rationale.

Then run:

```bash
python3 data/ic-support/benchmarks/nxp-kl25/gate58_review.py qualify \
  --run-dir /storage/projects/plasma-benchmark/nxp-kl25/bounded-primary-runs/20260909T080946Z \
  --verdict /storage/projects/plasma-benchmark/nxp-kl25/gate58/review-verdict.json \
  --output /storage/projects/plasma-benchmark/nxp-kl25/gate58/qualification-report.json
```

Qualification result:

```text
any NOT_REVIEWED dimension
    -> REVIEW_INCOMPLETE

all dimensions reviewed, any non-PASS dimension
    -> REJECTED_REVIEW

all retained facts:
  semantic_support    = SUPPORTED
  citation_entailment = COMPLETE
  atomicity           = PASS
  scope               = PASS
  terminology         = PASS
    -> QUALIFIED
```

`QUALIFIED` is scoped to this exact retained semantic run only.

## Admission boundary

Gate 5.8 may establish:

```text
exact retained Gate 5.7A semantic run = QUALIFIED
```

It does **not** establish:

```text
qwen3.8 model quality globally                 NO
all NXP KL25 parts qualified                   NO
canonical dataset admission                    NO
HIL                                            NO
production                                     NO
destructive security-operation admission       NO
```

The next product-engineering path after a successful Gate 5.8 review is canonicalization/profile integration, backend planning and Software Executor validation. Real MCU HIL and Production are outside the current MCU milestone.

## CI boundary

Repository CI executes only deterministic Gate 5.8 contract/view/verdict regression tests. It does not require:

- Ollama;
- model weights;
- external network access;
- a second Qwen inference;
- the private SWPC retained run.

The real retained run remains on SWPC and is consumed only by the explicit Gate 5.8 operator command.
