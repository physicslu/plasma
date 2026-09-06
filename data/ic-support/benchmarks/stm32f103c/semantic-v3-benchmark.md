# STM32F103C Structured Semantic Extraction v3 Benchmark

Status: research / engineering benchmark. No canonical-dataset or production admission.

## Why v3 exists

The retained v2 Qwen run completed successfully with:

- 21 asserted semantic leaves;
- 21/21 evidence mappings;
- zero uncited assertions;
- zero out-of-context citations;
- semantic score 20/21 = 95.24%.

The only v2 disagreement was `option_contract.encoding_semantics`. Qwen returned an evidence-grounded natural-language description of a primary option byte and a companion complement value. The v2 schema explicitly allowed a semantic description or label, while deterministic canonicalization only admitted a short exact alias set. Canonicalization therefore failed closed.

That failure exposed a contract gap, not permission to add the observed sentence to an alias list. v3 removes the ambiguity by representing option encoding as structured physical semantics.

The original v2 model artifact and v2 scoring remain retained evidence. They are not rewritten or rescored as v3 output.

## Architecture

```text
Locked Manufacturer Evidence
        |
        v
AI structured semantic extraction
        |
        | semantic-extraction-v1
        v
Structured manufacturer-near facts
        |
        v
Deterministic semantic mapping
        |
        | exact structured mapping only
        v
Existing deterministic canonicalization
        |
        v
Canonical IC Specification
```

The structured option facts are:

```text
logical_value_width_bits
stored_pair_width_bits
companion_value_present
companion_relation
```

`companion_relation` is a small vendor-neutral mathematical vocabulary. The generation prompt does not expose Plasma's canonical encoding label.

The deterministic boundary explicitly forbids:

- free-form text interpretation;
- substring matching;
- regex inference from prose;
- fuzzy semantic matching;
- adding observed model sentences as aliases.

A complete structure must match exactly one hidden admitted mapping. An incomplete structure remains unresolved. A complete but unrecognized structure fails closed.

## 1. Run the 64K Reduced structured extraction

Reuse the existing source-locked workspace:

```bash
python3 data/ic-support/benchmarks/stm32f103c/ollama_semantic_extraction_run_v3.py \
  --workspace /storage/projects/plasma-benchmark/stm32f103c-qwen/workspace \
  --output-dir /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v3 \
  --ollama-url http://127.0.0.1:11434 \
  --model qwen3.8:27b-mlx \
  --runtime-label mac-m3max-48gb-ollama-qwen3.8-27b-mlx-64k-semantic-v3 \
  --arm reduced_context \
  --num-ctx 65536 \
  --max-tokens 4096 \
  --temperature 0 \
  --seed 7 \
  --timeout-seconds 1800
```

Expected retained files:

```text
reduced_context.semantic-v3.raw.txt
reduced_context.semantic-v3.run.json
```

The generation path does not read:

- `semantic-extraction-ground-truth-v1.json`;
- `canonical-ground-truth-v1.json`;
- `canonicalization-contract-v1.json`;
- the v2 Qwen output or the v2 observed failure sentence.

## 2. Score structured semantic correctness

```bash
python3 data/ic-support/benchmarks/stm32f103c/score_semantic_extraction_v3.py \
  --run /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v3/reduced_context.semantic-v3.run.json \
  --output /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v3/semantic-score.json
```

The v3 semantic contract has 24 leaves. The option encoding structure contributes four exact semantic leaves instead of one free-form string. Hexadecimal address formatting remains representation-equivalent by integer value; option encoding no longer uses natural-language equivalence scoring.

A valid citation still proves only that the Evidence was supplied to the model. It does not mechanically prove semantic entailment.

## 3. Canonicalize the retained run

```bash
python3 data/ic-support/benchmarks/stm32f103c/canonicalize_semantic_run_v3.py \
  --run /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v3/reduced_context.semantic-v3.run.json \
  --output /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v3/canonical.json
```

The v3 canonicalization contract contains one exact structured mapping for the current locked STM32F103C evidence. The mapping contract is hidden from generation. Evidence for the canonical option-encoding field is the deterministic union of the evidence attached to the four structured semantic leaves.

## 4. Score canonical output

```bash
python3 data/ic-support/benchmarks/stm32f103c/score_canonical_v3.py \
  --canonical /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v3/canonical.json \
  --output /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v3/canonical-score.json
```

The canonical score remains a 25-leaf exact Plasma projection. Semantic correctness and canonical correctness remain separate measurements.

## Interpretation

The target result is not "make the score 100%". The target is a trustworthy classification boundary:

```text
AI semantic error
  != representation difference
  != deterministic mapping gap
  != canonicalization failure
```

If Qwen produces the correct four structured encoding facts, the v2 free-form contract gap is closed without teaching the deterministic layer to interpret English prose. If one or more structured facts are wrong, that becomes a real, inspectable semantic extraction failure.

Neither semantic nor canonical score authorizes production programming, destructive security transitions, option-byte writes, runtime admission, or HIL readiness.
