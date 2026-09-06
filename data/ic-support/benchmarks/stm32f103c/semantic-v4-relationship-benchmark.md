# STM32F103C Relationship Derivation v4 Benchmark

Status: research / engineering benchmark. No canonical-dataset, runtime, HIL, pin-level programming-hardware, or production admission.

## Why v4 exists

The retained v3 Qwen run proved the structured option-byte encoding path but left one unresolved semantic field:

```text
$.semantic_facts.profile_relationships.package_hardware = unknown
```

That result exposed a modeling problem. `package_hardware = shared` is not a manufacturer-near fact. It is a Plasma relationship obtained by comparing evidence-backed facts for the requested targets.

v4 therefore migrates **package_hardware relationship ownership** out of the AI semantic layer.

This is a foundation migration, not the final relationship architecture. The other four legacy profile relationship fields remain in the generation schema for this benchmark version so the scope stays bounded. Subsequent phases can migrate them only when their per-target/applicability inputs are defined with equivalent evidence and fail-closed semantics.

## Architecture

```text
Locked Manufacturer Evidence
        |
        v
AI semantic extraction
        |
        +--> per-target package family
        +--> per-target pin count
        +--> per-target debug/programming interfaces
        |
        v
Retained semantic artifact
        |
        v
Deterministic package-hardware relationship derivation
        |
        +--> complete + equal     -> shared
        +--> complete + unequal   -> different
        +--> incomplete           -> unknown
        |
        v
Structured option semantic mapping
        |
        v
Existing deterministic canonicalization
        |
        v
Canonical IC Specification
```

The AI cannot emit `profile_relationships.package_hardware`; the field does not exist in `semantic-extraction-v2.schema.json`.

## Package-hardware comparison contract

Each target emits only these manufacturer-near facts:

```text
package_family
pin_count
debug_programming_interfaces
```

For the v4 foundation:

- `package_family` is compared as an exact manufacturer-near package-family string;
- `pin_count` is compared as an exact positive integer;
- `debug_programming_interfaces` is selected from the schema vocabulary (`SWD`, `JTAG`) and compared as a set, so list order is representation-only;
- if any required package-hardware fact for either target is unknown/null, the relationship is `unknown`;
- complete unequal facts produce `different`;
- complete equal facts produce `shared`;
- no free-form text interpretation, substring matching, regex inference, or fuzzy matching is permitted.

The canonical relationship evidence is the deterministic union of citations attached to the per-target package-hardware facts.

The derived `package_hardware` relationship is explicitly a **benchmark profile projection** over these admitted fields. It does not prove that all pin-level minimum programming hardware is known or identical. The current package-hardware profile still treats pin-level minimum programming hardware as a separate evidence/admission problem.

## Trust boundary

Generation does not read:

- `semantic-extraction-ground-truth-v2.json`;
- `canonical-ground-truth-v2.json`;
- `canonicalization-contract-v2.json`;
- retained v3 model output or scores.

The v4 prompt explicitly asks for per-target facts and forbids the model from deciding the package-hardware relationship.

Citation presence still proves only that cited Evidence was supplied to the model. It does not mechanically prove semantic entailment.

## 1. Run the 64K Reduced extraction

```bash
python3 data/ic-support/benchmarks/stm32f103c/ollama_semantic_extraction_run_v4.py \
  --workspace /storage/projects/plasma-benchmark/stm32f103c-qwen/workspace \
  --output-dir /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v4 \
  --ollama-url http://127.0.0.1:11434 \
  --model qwen3.8:27b-mlx \
  --runtime-label mac-m3max-48gb-ollama-qwen3.8-27b-mlx-64k-semantic-v4 \
  --arm reduced_context \
  --num-ctx 65536 \
  --max-tokens 4096 \
  --temperature 0 \
  --seed 7 \
  --timeout-seconds 1800
```

Expected retained files:

```text
reduced_context.semantic-v4.raw.txt
reduced_context.semantic-v4.run.json
```

## 2. Score manufacturer-near semantic facts

```bash
python3 data/ic-support/benchmarks/stm32f103c/score_semantic_extraction_v4.py \
  --run /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v4/reduced_context.semantic-v4.run.json \
  --output /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v4/semantic-score.json
```

The v4 semantic contract has 29 leaves. `profile_relationships.package_hardware` is not one of them. The additional leaves are the per-target package-hardware facts.

## 3. Derive relationship and canonicalize

```bash
python3 data/ic-support/benchmarks/stm32f103c/canonicalize_semantic_run_v4.py \
  --run /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v4/reduced_context.semantic-v4.run.json \
  --output /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v4/canonical.json
```

The report records a `DETERMINISTIC_RELATIONSHIP_DERIVATION` transformation before structured option mapping and canonical normalization.

## 4. Score canonical output

```bash
python3 data/ic-support/benchmarks/stm32f103c/score_canonical_v4.py \
  --canonical /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v4/canonical.json \
  --output /storage/projects/plasma-benchmark/stm32f103c-qwen/semantic-v4/canonical-score.json
```

The canonical score remains 25 exact leaves. A complete correct package-hardware fact set can therefore produce `package_hardware = shared` without asking the model to emit the relationship itself.

## Interpretation

The target is not to maximize a benchmark percentage. The target is to place responsibility at the correct layer:

```text
Manufacturer facts
  !=
Cross-target relationship
  !=
Canonical representation
```

A v4 result should be classified as one of:

```text
AI fact extraction error
AI fact unknown / insufficient evidence
Deterministic relationship result
Deterministic mapping/canonicalization result
```

Do not collapse those categories into one accuracy number.

No result from this benchmark authorizes production programming, option-byte writes, destructive security transitions, runtime admission, HIL readiness, pin-level minimum programming-hardware readiness, or real-target behavior.
