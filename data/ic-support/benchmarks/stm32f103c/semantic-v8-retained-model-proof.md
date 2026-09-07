# STM32F103C Semantic v8 — Retained Qwen Model Proof

Status: execution/verification contract for a retained local-model benchmark. This document does not claim that a v8 Qwen run has already been executed.

## Purpose

The v8 deterministic pipeline is already covered by CI. This phase proves a different question:

> Can the actual `qwen3.8:27b-mlx` model produce the v8 manufacturer-near fact contract, with zero AI-emitted profile relationships, while the deterministic pipeline still reaches the exact canonical result?

A retained model proof is valid only when the generated artifacts pass `retained_semantic_v8.py`.

## Fixed execution identity

```text
model        = qwen3.8:27b-mlx
arm          = reduced_context
num_ctx      = 65536
temperature  = 0
seed         = 7
max_tokens   = 4096
```

These values are part of the retained-proof identity. A run with different values may be useful research, but it is not this proof.

## One-command execution

Run on the host that can reach the Mac Ollama endpoint and has the prepared benchmark workspace:

```bash
python3 data/ic-support/benchmarks/stm32f103c/retained_semantic_v8.py \
  --workspace /storage/projects/plasma-benchmark/stm32f103c-qwen/workspace \
  --output-dir /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v8 \
  --ollama-url http://127.0.0.1:11434 \
  --runtime-label mac-m3max-48gb-ollama-qwen3.8-27b-mlx-64k-semantic-v8 \
  --timeout-seconds 1800
```

Expected retained artifacts:

```text
reduced_context.semantic-v8.raw.txt
reduced_context.semantic-v8.run.json
semantic-score.json
canonical.json
canonical-score.json
retained-proof-manifest.json
```

## Verification-only mode

An existing artifact directory can be reverified without contacting Ollama:

```bash
python3 data/ic-support/benchmarks/stm32f103c/retained_semantic_v8.py \
  --output-dir /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v8 \
  --verify-only
```

## Admission criteria

`verified_retained_model_proof` requires all of the following:

- exact model identity `qwen3.8:27b-mlx`;
- reduced context, 64K, temperature 0, seed 7;
- AI `profile_relationships` is exactly `{}`;
- semantic accuracy = 1.0;
- semantic wrong = 0;
- semantic missing/unknown = 0;
- semantic uncited = 0;
- semantic out-of-context citations = 0;
- canonical exact accuracy = 1.0;
- canonical wrong = 0;
- canonical missing/unknown = 0;
- canonical uncited = 0;
- canonical out-of-context citations = 0;
- deterministic relationships are exactly:
  - programming = shared
  - option = shared
  - security = shared
  - memory_geometry = different
  - package_hardware = shared
- canonical dataset admission = false;
- production admission = false;
- destructive security operation admission = false;
- HIL admission = false.

The manifest records SHA-256 identities for the five primary retained artifacts.

## Interpretation

Passing this proof means the actual local model can satisfy the current STM32F103C v8 extraction contract and feed the deterministic canonicalization pipeline without owning any profile relationship.

It still does **not** prove:

- cross-vendor generality;
- HIL behavior;
- FPGA/SWD timing correctness;
- real IC programming correctness;
- destructive security-transition safety;
- canonical dataset admission;
- production admission.
