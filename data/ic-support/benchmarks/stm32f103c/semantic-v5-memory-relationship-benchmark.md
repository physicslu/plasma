# STM32F103C Semantic v5 — Memory Geometry Relationship Derivation Foundation

Status: Research / engineering foundation

## Purpose

v5 removes `profile_relationships.memory_geometry` from AI generation and derives it deterministically from evidence-backed per-target memory facts.

The generation boundary is now:

```text
Manufacturer Evidence
  -> AI per-target semantic facts
  -> deterministic memory_geometry derivation
  -> deterministic package_hardware derivation
  -> deterministic canonicalization
  -> Canonical IC Spec
```

The AI does not emit either `memory_geometry` or `package_hardware` as `shared|different|unknown`.

## Memory relationship contract

Per target inputs:

```text
flash_size_bytes
page_size_bytes
page_count
```

Rules:

```text
complete + equal   -> shared
complete + unequal -> different
incomplete         -> unknown
```

No free-form matching, substring inference, regex semantic inference, or fuzzy relationship matching is allowed.

For the locked benchmark targets:

```text
STM32F103C8T6: flash=65536, page=1024, count=64
STM32F103CBT6: flash=131072, page=1024, count=128
```

The expected deterministic relationship is therefore:

```text
memory_geometry = different
```

## Versioning

v4 artifacts and contracts remain immutable. v5 uses new generation schema/prompt, ground-truth projections, canonicalization contract, runner, scorers, and regression tests.

Relevant files:

```text
semantic-extraction-v3.schema.json
semantic-extraction-prompt-v3.txt
semantic_extraction_v5.py
ollama_semantic_extraction_run_v5.py
semantic-extraction-ground-truth-v3.json
score_semantic_extraction_v5.py
canonicalization-contract-v3.json
canonicalize_semantic_facts_v5.py
canonicalize_semantic_run_v5.py
canonical-ground-truth-v3.json
score_canonical_v5.py
test_semantic_v5_memory_relationship_pipeline.py
```

## Trust boundary

This phase does not authorize or prove:

- canonical dataset admission;
- production admission;
- HIL or real-target programming;
- FPGA or SWD backend correctness;
- programming/option/security relationship migration;
- destructive security transitions.

Citation presence proves evidence availability, not mechanical semantic entailment.
