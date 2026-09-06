# STM32F103C semantic extraction and canonicalization foundation

Status: benchmark/research foundation only

This document defines the first executable separation between manufacturer-near AI extraction and Plasma canonical specification representation.

## Why this boundary exists

The retained 64K Reduced extraction produced 21 asserted fields with 21 in-context evidence mappings. Four fields did not exact-match the benchmark ground truth:

- manufacturer reference `STM32F103x8` versus Plasma commercial-part base `STM32F103C8`;
- manufacturer reference `STM32F103xB` versus Plasma commercial-part base `STM32F103CB`;
- manufacturer-formatted address `0x1FFF F800` versus canonical `0x1FFFF800`;
- semantic label `complemented` versus canonical vocabulary `byte_plus_complement`.

Those mismatches are not all the same class. Treating them all as AI factual errors forces the model to guess internal representation policy and makes the benchmark conflate evidence interpretation with deterministic normalization.

The foundation therefore separates:

```text
Locked Manufacturer Evidence
        |
        v
AI semantic extraction
        |
        | evidence-backed, manufacturer-near facts
        v
semantic-extraction-v0
        |
        v
Deterministic canonicalization
        |
        v
canonical-spec-v0
        |
        v
Semantic validation / later admission gates
```

## Artifact roles

`semantic-extraction.schema.json`

- is the AI-side semantic contract;
- preserves `manufacturer_device_reference` separately from commercial-part identity;
- accepts manufacturer-near hexadecimal text such as `0x1FFF F800`;
- accepts evidence-backed option-encoding semantics without requiring Plasma's internal controlled vocabulary;
- permits `null` / `unknown` where evidence is insufficient.

`canonicalization-contract-v0.json`

- is not visible to the AI generation step;
- owns deterministic commercial-part identity context;
- owns hexadecimal representation rules;
- owns controlled-vocabulary aliases;
- records evidence authority for identity fields introduced by deterministic context;
- does not grant canonical-dataset or production admission.

`canonical-spec.schema.json`

- is the deterministic Plasma representation after canonicalization;
- keeps manufacturer reference and commercial-part base as separate fields;
- requires normalized hexadecimal address representation;
- requires controlled vocabulary for option encoding.

`canonicalize_semantic_facts.py`

- validates the v0 semantic shape without reading benchmark ground truth;
- normalizes hexadecimal representation;
- maps admitted semantic aliases to controlled vocabulary;
- introduces commercial-part identity only from deterministic target context;
- propagates AI evidence to every canonical field derived from an AI fact;
- attaches deterministic authority citations to identity fields introduced by the canonicalization contract;
- fails closed for unknown non-null controlled-vocabulary values or asserted semantic facts without evidence.

## Identity semantics

The old benchmark field `base_device` was ambiguous. The new model separates three concepts:

```text
manufacturer_device_reference = STM32F103x8
commercial_part_base           = STM32F103C8
icpn                           = STM32F103C8T6
```

The AI extractor may report the manufacturer reference when supported by evidence. It does not infer `commercial_part_base`. The canonicalizer obtains `commercial_part_base` from evidence-backed deterministic target identity context.

This is intentional. Across manufacturers, family/reference labels and commercial ordering stems are not guaranteed to have one universal string transformation.

## Representation normalization

A hexadecimal address is a number with a representation policy, not a natural-language fact. For example:

```text
AI semantic fact:   0x1FFF F800
canonical value:    0x1FFFF800
```

`canonicalize_semantic_facts.py` removes whitespace, verifies hexadecimal syntax, parses the integer, and emits a lowercase `0x` prefix with uppercase digits and no leading zero padding.

This keeps trivial formatting policy out of the model correctness score.

## Controlled vocabulary

The canonicalization contract currently admits the following semantic aliases for the option-byte encoding:

```text
byte_plus_complement
complemented
byte plus complement
byte+complement
byte + complement
        -> byte_plus_complement
```

An unrecognized non-null label fails closed. The canonicalizer does not use fuzzy similarity or model judgment to invent an alias.

Future manufacturer support should add aliases only when the engineering meaning is explicitly reviewed. The mapping is a governance artifact, not an AI guess.

## Evidence preservation

Canonicalization must not erase provenance.

For copied or normalized AI facts:

```text
$.semantic_facts.option_contract.region_start_text
        |
        | same manufacturer citation(s)
        v
$.canonical_spec.option_contract.region_start
```

For deterministic identity context:

```text
target ICPN + admitted identity context
        |
        | contract authority citation
        v
$.canonical_spec.targets.<ICPN>.commercial_part_base
```

The foundation therefore makes evidence propagation executable rather than descriptive.

## Legacy benchmark bridge

`legacy_benchmark_projection()` projects `canonical-spec-v0` back into the existing v0 benchmark score shape only for regression comparison. In that projection:

```text
canonical commercial_part_base -> legacy base_device
```

This bridge does not make the old ambiguous field canonical again. New extraction work should use the semantic/canonical split.

## Trust boundary

This foundation does **not** authorize or claim:

- canonical dataset admission;
- production IC support admission;
- driver generation correctness;
- HIL or real-target programming readiness;
- semantic entailment proof merely because a cited page is in context;
- a universal cross-manufacturer identifier-normalization algorithm.

The next meaningful runtime experiment is to make a fresh model extraction target `semantic-extraction-v0`, then canonicalize the retained result deterministically and evaluate semantic correctness separately from representation correctness.
