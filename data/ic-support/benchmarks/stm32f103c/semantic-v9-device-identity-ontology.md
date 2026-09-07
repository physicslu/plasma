# STM32F103C Semantic v9 — Device Identity Ontology Foundation

## Why v9 exists

The first actual v8 Qwen retained run completed successfully at the transport/schema/evidence layers but scored 23/25 semantic leaves. The only two wrong fields were the ambiguous `manufacturer_device_reference` leaves:

```text
STM32F103C8T6 -> STM32F103C8T6
STM32F103CBT6 -> STM32F103CBT6
```

The v8 ground truth expected manufacturer document applicability expressions:

```text
STM32F103C8T6 -> STM32F103x8
STM32F103CBT6 -> STM32F103xB
```

This exposed an ontology problem, not a reason to relax scoring.

## Identity model

v9 separates two concepts that v8 named too loosely:

```text
requested commercial identity
    = semantic_facts.targets object key
    = STM32F103C8T6 / STM32F103CBT6

manufacturer applicability expression
    = AI-extracted evidence-backed manufacturer scope expression
    = STM32F103x8 / STM32F103xB
```

The commercial ICPN is already an input identity. It is not duplicated as an AI-generated leaf.

The semantic field is therefore renamed:

```text
manufacturer_device_reference
    -> manufacturer_applicability_expression
```

## Strict semantic rule

The scorer does not treat a commercial ICPN as equivalent to a manufacturer applicability expression.

```text
STM32F103C8T6 != STM32F103x8
```

for semantic scoring purposes. They represent different ontology roles. No fuzzy, substring, regex, or alias normalization is permitted to hide the distinction.

If the model copies the requested commercial ICPN into `manufacturer_applicability_expression`, that remains a semantic error.

## Canonical compatibility

The canonical schema is intentionally unchanged. A deterministic ontology projection maps:

```text
semantic manufacturer_applicability_expression
        ->
canonical manufacturer_device_reference
```

This preserves the existing canonical contract while making the AI-side semantic role explicit.

The projection is exact and evidence-preserving. It is not identity inference.

## Relationship ownership

v9 retains the v8 architecture:

- programming relationship: deterministic applicability derivation;
- option relationship: deterministic applicability derivation;
- security relationship: deterministic applicability derivation;
- memory geometry relationship: deterministic comparison;
- package hardware relationship: deterministic comparison;
- AI emits zero profile relationships.

## Retained proof

The v9 retained proof remains strict:

```text
model       = qwen3.8:27b-mlx
arm         = reduced_context
num_ctx     = 65536
temperature = 0
seed        = 7
semantic    = 25/25 required
canonical   = 25/25 required
```

Run on SWPC with the existing Mac Ollama tunnel:

```bash
python3 data/ic-support/benchmarks/stm32f103c/retained_semantic_v9.py \
  --workspace /storage/projects/plasma-benchmark/stm32f103c-qwen/workspace \
  --output-dir /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v9 \
  --ollama-url http://127.0.0.1:11434 \
  --runtime-label mac-m3max-48gb-ollama-qwen3.8-27b-mlx-64k-semantic-v9 \
  --timeout-seconds 1800
```

A successful command produces `retained-proof-manifest.json` with status `verified_retained_model_proof`.

## Safety and admission boundary

This phase does not authorize:

- canonical dataset admission;
- production admission;
- HIL admission;
- FPGA or SWD runtime admission;
- real IC programming;
- option-byte writes;
- RDP transitions;
- destructive security operations.

The v8 92% run remains valid historical evidence that motivated this ontology correction. It must not be rewritten into a passing v8 result.
