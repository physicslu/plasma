# NXP KL25 Live Model Qualification

Target: `MKL25Z128VLK4`

This document defines the bounded live-model experiment that follows the admitted model-free semantic runner CI.

## Qualification objective

The experiment evaluates one exact local-model runtime against the already admitted KL25 Evidence Pack / TargetEvidenceBundle input. It does not rediscover source identity, applicability, or Evidence Pack membership.

The qualification pipeline is:

```text
retained Gate 3 Evidence Pack workspace
  -> validate exact target/bundle/pre-AI digests
  -> enforce loopback-only Ollama endpoint
  -> lock Ollama version + exact model digest
  -> execute qwen3.8:27b-mlx with frozen generation settings
  -> retain raw response + semantic-run artifact + provenance
  -> deterministic integrity checks
  -> deterministic semantic defect screening
  -> manufacturer-evidence review
  -> QUALIFIED only after all three layers pass
```

A valid JSON response is not semantic qualification. A deterministic screening pass is also not proof of factual correctness.

## Frozen experiment

`live-model-qualification-contract.json` freezes:

- exact target: `MKL25Z128VLK4`;
- Gate 3 target-bundle digest;
- Gate 3 pre-AI manifest digest;
- semantic extraction contract ID;
- transport: `ollama_native_chat`;
- model: `qwen3.8:27b-mlx`;
- runtime label: `kl25-live-model-qualification`;
- context: 32768 tokens;
- maximum output: 4096 tokens;
- temperature: 0.0;
- seed: 0;
- timeout: 1800 seconds.

The Ollama endpoint is restricted to HTTP loopback (`127.0.0.1`, `localhost`, or `::1`). Remote provider URLs, embedded credentials, HTTPS endpoints, and non-root URL paths are rejected by this experiment contract.

Before inference, `ollama_live_runtime.py` queries `/api/version` and `/api/tags`. The run provenance records the Ollama version and exact model digest. The model tag alone is not considered immutable model identity.

## Deterministic screening

The live output must first pass the Gate 4 strict JSON/citation contract. Gate 5 then adds qualification-specific screening:

- all eight primary Evidence Units must return `FACTS` rather than `UNKNOWN`;
- each unit must contain at least one fact;
- each unit must cite at least one physical page belonging to its primary Evidence Unit, not dependency pages only;
- key NXP-native concepts required for each unit must be present;
- STM32-specific projection terms such as `FLASH_CR` and `KEYR` are rejected;
- `raw-response.txt` must reparse to exactly the same JSON object retained in `semantic-run.json`;
- runtime/model/provenance identities and frozen generation settings must match the qualification contract.

These checks are defect filters. They can detect obvious omission, ontology contamination, citation misuse, runtime drift, and artifact tampering. They cannot prove that every free-text statement is technically correct.

## Manufacturer-evidence review

A run that passes deterministic integrity and semantic screening becomes `READY_FOR_REVIEW`, not `QUALIFIED`.

Final qualification requires an exact per-unit reviewed verdict bound to the semantic-run digest. The review basis must be the bounded manufacturer evidence. All eight unit verdicts must be `PASS` for the overall verdict to be `PASS`.

The review must challenge, at minimum:

- whether every material statement is supported by the cited NXP pages;
- whether command prerequisites and completion/error semantics are preserved;
- whether security and mass-erase constraints are stated without widening applicability;
- whether debug/security behavior distinguishes normal SWD access from secure-state MDM-AP recovery behavior;
- whether any cross-vendor or synthesized identity concept entered the output.

Model agreement is not a substitute for this evidence review.

## Local execution

The actual model-weight inference must run on a host that owns the local Ollama runtime and the exact Gate 3 Evidence Pack output directory.

From the repository root, the executable path is:

```bash
python data/ic-support/benchmarks/nxp-kl25/run_live_model_qualification.py \
  --input-dir <exact-gate3-evidence-pack-output> \
  --output-dir <new-live-qualification-output> \
  --ollama-url http://127.0.0.1:11434
```

Do not substitute a different model, context length, seed, timeout, provider, or Gate 3 workspace while calling the result the same experiment. A changed condition is a different run and must be identified as such.

The output directory contains:

```text
semantic-run.json
raw-response.txt
live-run-provenance.json
qualification-report.json
```

Expected successful pre-review status:

```text
READY_FOR_REVIEW
```

`QUALIFIED` requires a separate reviewed semantic verdict bound to the exact `semantic_run_digest`.

## Trust boundary

Admitted after model-free CI:

- live-model qualification harness.

Not admitted merely because the harness exists:

- a real live-model run;
- semantic extraction quality;
- canonical dataset;
- HIL;
- production programming;
- destructive security operations.

The repository CI intentionally does not load model weights or claim access to the user's local Ollama runtime.
