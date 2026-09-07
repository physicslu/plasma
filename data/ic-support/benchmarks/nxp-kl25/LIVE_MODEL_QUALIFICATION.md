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
  -> require provider-side JSON Schema structured output
  -> retain raw response + semantic-run artifact + provider metadata + provenance
  -> deterministic integrity checks
  -> deterministic semantic defect screening
  -> manufacturer-evidence review
  -> QUALIFIED only after all three layers pass
```

A valid JSON response is not semantic qualification. A deterministic screening pass is also not proof of factual correctness.

## Frozen experiment v1

`live-model-qualification-contract.json` freezes:

- contract ID: `nxp-kl25-live-model-qualification-v1`;
- exact target: `MKL25Z128VLK4`;
- Gate 3 target-bundle digest;
- Gate 3 pre-AI manifest digest;
- semantic extraction contract ID;
- transport: `ollama_native_chat`;
- model: `qwen3.8:27b-mlx`;
- runtime label: `kl25-live-model-qualification`;
- output protocol: Ollama `format=<JSON Schema>` structured output;
- exactly one final JSON document; reasoning / `<think>` content is forbidden in the answer channel;
- context: 32768 tokens;
- maximum output: 4096 tokens;
- temperature: 0.0;
- seed: 0;
- timeout: 1800 seconds.

The v1 output protocol is a deliberate experiment change after the first real v0 run showed that prompt-only JSON instructions were not sufficient. The generation settings were not widened to hide that failure.

The provider-facing JSON Schema constrains representation shape, including an evidence citation object of the form:

```json
{
  "source_id": "nxp_kl25_rm_rev3",
  "pdf_page_number": 150
}
```

Provider-side structured decoding is not a trust boundary. The deterministic parser still owns exact unit coverage, FACTS/UNKNOWN semantics, fact-kind validation, exact citation membership in each Evidence Pack, and fail-closed behavior.

## First real v0 negative run

The first actual `qwen3.8:27b-mlx` run reached the model and returned content, but failed the prompt-only output contract before semantic qualification.

Observed failure class:

```text
model_output_invalid_json
```

The retained raw response began with one complete JSON document, then contained a `</think>` marker followed by a second JSON document that was truncated. The first JSON document also used string citations such as `nxp_kl25_rm_rev3:p150` instead of the required evidence-object representation.

This negative result must not be repaired in place. Do not strip thinking markers, select the first JSON object, rewrite citations, or otherwise mutate the raw response into a passing artifact. It is evidence that the v0 prompt-only output protocol was insufficient for this exact model/runtime/run.

Gate 5.1 therefore hardens the output protocol instead of pretending the first run passed.

## Runtime topology

The benchmark authority remains on SWPC:

```text
SWPC
  /storage/projects/plasma
  /storage/projects/plasma-benchmark/nxp-kl25
      source/
      pre-ai/
      runs/
```

The Mac owns the local Ollama/model runtime. SWPC reaches it through the established SSH reverse tunnel, so the qualification process still connects only to:

```text
http://127.0.0.1:11434
```

The loopback-only rule therefore does not require copying the benchmark workspace to the Mac. Do not expose Ollama directly on a LAN address for this qualification path.

## Deterministic screening

The live output must first pass the strict JSON/citation contract. Gate 5 then adds qualification-specific screening:

- all eight primary Evidence Units must return `FACTS` rather than `UNKNOWN`;
- each unit must contain at least one fact;
- each unit must cite at least one physical page belonging to its primary Evidence Unit, not dependency pages only;
- key NXP-native concepts required for each unit must be present;
- STM32-specific projection terms such as `FLASH_CR` and `KEYR` are rejected;
- `raw-response.txt` must reparse to exactly the same JSON object retained in `semantic-run.json`;
- runtime/model/provenance identities and frozen generation settings must match the qualification contract.

These checks are defect filters. They can detect obvious omission, ontology contamination, citation misuse, runtime drift, and artifact tampering. They cannot prove that every free-text statement is technically correct.

## Provider metadata on model-output failure

Provider completion metadata is retained as soon as a valid Ollama transport response is received, before semantic JSON parsing. Therefore a malformed model document no longer erases evidence such as:

```text
response_model
done
done_reason
input_tokens
generation_tokens
timing
```

This separates the root model-output failure from secondary qualification symptoms. A malformed semantic document still fails closed and no partial facts are admitted.

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

## SWPC operator helper

Repeated operator steps are consolidated in one repository helper:

```bash
bash scripts/ic-support-kl25-live.sh status
bash scripts/ic-support-kl25-live.sh build
bash scripts/ic-support-kl25-live.sh run
bash scripts/ic-support-kl25-live.sh diagnose
```

Default storage root:

```text
/storage/projects/plasma-benchmark/nxp-kl25
```

`status` validates the exact pre-AI workspace and verifies the loopback Ollama endpoint, exact model ID, and model digest.

`build` rebuilds the Gate-3 pre-AI workspace from the source-locked PDFs using a temporary directory and only replaces `pre-ai/` after a successful deterministic build.

`run` never reuses a prior qualification output directory. Each invocation writes a new UTC-identified directory:

```text
/storage/projects/plasma-benchmark/nxp-kl25/runs/<UTC-run-id>/
```

and updates `runs/latest` as a convenience pointer. Failed runs are retained rather than overwritten.

`diagnose` is read-only. It reports single-document JSON status, trailing/duplicate content, thinking markers, semantic-run error class, provider completion metadata, qualification integrity errors, and—when a first complete JSON document exists—whether that first document would satisfy the deterministic semantic contract. Diagnostic parsing never changes the retained raw response.

The helper also recognizes the original legacy path `/storage/projects/plasma-benchmark/nxp-kl25/qwen-live/` for diagnosis so the first negative run remains inspectable.

## Direct executable path

The lower-level executable remains available for controlled testing:

```bash
python3 data/ic-support/benchmarks/nxp-kl25/run_live_model_qualification.py \
  --input-dir /storage/projects/plasma-benchmark/nxp-kl25/pre-ai \
  --output-dir <new-unique-output-directory> \
  --ollama-url http://127.0.0.1:11434
```

Do not substitute a different model, context length, seed, timeout, provider, or Gate 3 workspace while calling the result the same experiment. A changed condition is a different run and must be identified as such.

Each run directory contains:

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

- live-model qualification harness;
- structured-output transport and deterministic output-schema generation under mocked CI;
- operator helper syntax and fail-closed orchestration under non-model CI.

Not admitted merely because the harness exists:

- a successful real v1 live-model run;
- semantic extraction quality;
- canonical dataset;
- HIL;
- production programming;
- destructive security operations.

Repository CI intentionally does not load model weights or claim access to the operator's local Ollama runtime.
