# STM32F103C Semantic Extraction v2 Benchmark

Status: research / engineering benchmark. No canonical-dataset or production admission.

## Purpose

The retained v0 extraction mixed manufacturer facts with Plasma canonical representation. A technically meaningful manufacturer answer could therefore fail exact-match scoring because of identifier naming, hexadecimal formatting, or controlled vocabulary.

v2 separates those concerns:

```text
Locked Manufacturer Evidence
        |
        v
AI semantic extraction
        |
        | semantic-extraction-v0
        v
Manufacturer-near Semantic Facts
        |
        | retained artifact boundary
        v
Deterministic canonicalization
        |
        | stm32f103c-canonicalization-v0
        v
Canonical IC Specification
        |
        v
Separate semantic and canonical scoring
```

The generation path does not read either v2 ground-truth file or `canonicalization-contract-v0.json`.

## 1. Run manufacturer-near semantic extraction

Reuse the already prepared source-locked A/B workspace. For the measured 64K Reduced operating point:

```bash
python data/ic-support/benchmarks/stm32f103c/ollama_semantic_extraction_run.py \
  --workspace /storage/projects/plasma-benchmark/stm32f103c-qwen/workspace \
  --output-dir /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v2 \
  --ollama-url http://127.0.0.1:11434 \
  --model qwen3.8:27b-mlx \
  --runtime-label mac-m3max-48gb-ollama-qwen3.8-27b-mlx-64k-semantic-v2 \
  --arm reduced_context \
  --num-ctx 65536 \
  --max-tokens 4096 \
  --temperature 0 \
  --seed 7 \
  --timeout-seconds 1800
```

The model returns exactly:

```text
semantic_facts + evidence
```

`manufacturer_device_reference`, `region_start_text`, and `encoding_semantics` intentionally remain manufacturer-near. The model is not asked to infer `commercial_part_base` or select Plasma canonical option-encoding vocabulary.

The run fails closed if the semantic schema is violated, asserted leaves lack evidence, evidence paths do not exactly match asserted leaves, or a citation is outside the supplied source/page set.

## 2. Score semantic extraction

Score the retained model artifact separately:

```bash
python data/ic-support/benchmarks/stm32f103c/score_semantic_extraction_v2.py \
  --run /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v2/reduced_context.semantic.run.json \
  --output /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v2/semantic-score.json
```

The semantic score distinguishes:

- semantic correctness;
- literal representation agreement;
- representation-only differences;
- missing/unknown facts;
- citation coverage and in-context validity.

For `region_start_text`, hexadecimal strings are compared by integer meaning. For `encoding_semantics`, admitted semantic aliases are compared by the hidden scoring/canonicalization contract. These rules are not generation inputs.

A valid in-context citation proves only that the cited Evidence was supplied. It does not mechanically prove semantic entailment.

## 3. Deterministically canonicalize the retained run

Only after the model result exists as a retained artifact:

```bash
python data/ic-support/benchmarks/stm32f103c/canonicalize_semantic_run.py \
  --run /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v2/reduced_context.semantic.run.json \
  --output /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v2/canonical.json
```

Canonicalization owns:

- deterministic commercial-part identity context;
- hexadecimal representation normalization;
- controlled-vocabulary mapping;
- evidence propagation into transformed canonical fields.

Unknown non-null controlled vocabulary fails closed. Canonicalization does not turn an unsupported model fact into a supported fact.

## 4. Score canonical output

```bash
python data/ic-support/benchmarks/stm32f103c/score_canonical_v2.py \
  --canonical /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v2/canonical.json \
  --output /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v2/canonical-score.json
```

The canonical score evaluates all 25 canonical leaves, including deterministic ICPN and commercial-part identity fields, using exact canonical representation.

## Interpretation

The two scores answer different questions:

```text
Semantic score
  -> Did the AI recover the manufacturer-grounded technical meaning?

Canonical score
  -> Did deterministic canonicalization produce the exact Plasma projection?
```

Do not collapse them into one accuracy number. A semantic error remains an AI/evidence-extraction problem even if a formatter could produce a syntactically canonical value. A representation-only difference should not be mislabeled as a manufacturer-fact hallucination.

Neither score is production admission. Real-target programming, security transitions, option-byte operations, implementation validity, and HIL remain separate gates.
