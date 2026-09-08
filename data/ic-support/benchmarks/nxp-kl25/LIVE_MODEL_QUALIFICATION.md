# NXP KL25 Live Model Qualification

Target: `MKL25Z128VLK4`

This document defines the bounded live-model experiment that follows the admitted model-free semantic runner CI.

## Qualification objective

The experiment evaluates one exact local-model runtime against the already admitted KL25 Evidence Pack / TargetEvidenceBundle input. It does not rediscover source identity, applicability, or Evidence Pack membership.

The qualification pipeline is:

```text
retained Gate 3 Evidence Pack workspace
  -> validate exact target/bundle/pre-AI digests
  -> deterministic inference-only physical-page compaction
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

## Frozen experiment v2

`live-model-qualification-contract.json` freezes:

- contract ID: `nxp-kl25-live-model-qualification-v2`;
- exact target: `MKL25Z128VLK4`;
- Gate 3 target-bundle digest;
- Gate 3 pre-AI manifest digest;
- semantic extraction contract ID;
- transport: `ollama_native_chat`;
- model: `qwen3.8:27b-mlx`;
- runtime label: `kl25-live-model-qualification`;
- context strategy: `cross_pack_physical_page_dedup_v1`;
- output protocol: Ollama `format=<JSON Schema>` structured output;
- exactly one final JSON document; reasoning / `<think>` content is forbidden in the answer channel;
- context: 65536 tokens;
- maximum output: 8192 tokens;
- temperature: 0.0;
- seed: 0;
- timeout: 1800 seconds.

Gate 5.2 keeps every admitted Gate-3 Evidence Pack and retained digest unchanged. Compaction is an inference-only deterministic transformation: repeated physical pages present in multiple dependency-closed Evidence Packs are validated and materialized once. Per-unit citation authority remains the original Evidence Pack membership and is still enforced by the deterministic parser.

The provider-facing JSON Schema constrains representation shape, including an evidence citation object of the form:

```json
{
  "source_id": "nxp_kl25_rm_rev3",
  "pdf_page_number": 150
}
```

Provider-side structured decoding is not a trust boundary. The deterministic parser still owns exact unit coverage, FACTS/UNKNOWN semantics, fact-kind validation, exact citation membership in each Evidence Pack, and fail-closed behavior.

## Retained negative evolution

### v0 — prompt-only output contract

The first actual `qwen3.8:27b-mlx` run reached the model and returned content, but failed before semantic qualification with `model_output_invalid_json`. The retained raw response contained one complete JSON document, a `</think>` marker, then a second truncated JSON document. The first JSON also encoded citations as strings instead of evidence objects.

This negative result remains immutable. Gate 5.1 introduced provider-side JSON Schema structured output rather than repairing the retained response.

### v1 — structured output, monolithic repeated context

The first v1 structured-output run removed the v0 answer-shape failures, but ended with:

```text
semantic_status       = error
qualification_status  = REJECTED_INTEGRITY
provider_done_reason  = length
provider_input_tokens = 86131
generation_tokens     = 4096
```

A subsequent read-only context audit established:

```text
page_occurrences          = 127
unique_physical_pages     = 33
duplicate_occurrences     = 94
occurrence_redundancy_pct = 74.02
current_context_bytes     = 413754
dedup_context_bytes       = 107285
current_prompt_bytes      = 419030
dedup_prompt_bytes        = 112561
```

The dominant input inflation was therefore cross-Pack repeated dependency evidence, not an intrinsic requirement for an 86K manufacturer context.

### v2 — compact context reaches semantic screening

The first real v2 run was retained at:

```text
/storage/projects/plasma-benchmark/nxp-kl25/runs/20260908T004912Z
```

Observed execution evidence:

```text
context_strategy                = cross_pack_physical_page_dedup_v1
context_page_occurrences        = 127
context_unique_physical_pages   = 33
context_duplicates_removed      = 94
context_bytes                   = 107386
legacy_context_bytes            = 413754
prompt_bytes                    = 112662
provider_input_tokens           = 23237
provider_generation_tokens      = 3266
provider_done_reason            = stop
requested_num_ctx               = 65536
requested_max_tokens            = 8192
FULL_JSON                       = PASS
FIRST_DOCUMENT_SEMANTIC_CONTRACT = PASS
semantic_status                 = success
integrity_errors                = []
qualification_status            = REJECTED_SCREENING
```

This result closes the prior context/runtime failure class: the compact prompt completed well inside the requested 64K/8192 envelope, produced one valid structured JSON document, and passed the deterministic semantic parser and qualification integrity layer. It does **not** establish semantic correctness. The run is retained as the first v2 semantic-screening negative result and must not be mutated or rerun merely to replace it.

The exact semantic-screening errors are retained in `qualification-report.json`; the operator `diagnose` command prints them directly so the next engineering decision can distinguish model-content omission from a screening-contract problem.

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

The loopback-only rule does not require copying the benchmark workspace to the Mac. Do not expose Ollama directly on a LAN address for this qualification path.

## Deterministic screening

The live output must first pass the strict JSON/citation contract. Qualification-specific screening then requires:

- all eight primary Evidence Units return `FACTS` rather than `UNKNOWN`;
- each unit contains at least one fact;
- each unit cites at least one physical page belonging to its primary Evidence Unit, not dependency pages only;
- key NXP-native concepts required for each unit are present;
- STM32-specific projection terms such as `FLASH_CR` and `KEYR` are rejected;
- `raw-response.txt` reparses to exactly the same JSON object retained in `semantic-run.json`;
- runtime/model/provenance identities and frozen generation settings match the qualification contract;
- provider-reported input tokens remain inside the requested context window;
- provider-reported input plus generated tokens remain inside the requested context envelope.

These checks are defect filters. They can detect omission, ontology contamination, citation misuse, runtime drift, and artifact tampering. They cannot prove that every free-text statement is technically correct.

## Provider metadata on model-output failure

Provider completion metadata is retained as soon as a valid Ollama transport response is received, before semantic JSON parsing. Therefore a malformed model document does not erase evidence such as:

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
bash scripts/ic-support-kl25-live.sh context-audit
bash scripts/ic-support-kl25-live.sh build
bash scripts/ic-support-kl25-live.sh run
bash scripts/ic-support-kl25-live.sh diagnose
```

Default storage root:

```text
/storage/projects/plasma-benchmark/nxp-kl25
```

`status` validates the exact pre-AI workspace, frozen context/generation envelope, and loopback Ollama/model identity.

`context-audit` measures legacy versus compact context deterministically without invoking model inference.

`build` rebuilds the Gate-3 pre-AI workspace from source-locked PDFs using a temporary directory and only replaces `pre-ai/` after a successful deterministic build.

`run` never reuses a prior qualification output directory. Each invocation writes a new UTC-identified directory under `runs/` and updates `runs/latest` as a convenience pointer. Failed runs are retained rather than overwritten.

`diagnose` is read-only. It reports single-document JSON status, trailing/duplicate content, thinking markers, context compaction metrics, semantic-run error class, provider completion metadata, requested runtime envelope, qualification integrity errors, semantic-screening errors, and review status. Diagnostic parsing never changes the retained raw response.

The helper also recognizes the original legacy path `/storage/projects/plasma-benchmark/nxp-kl25/qwen-live/` for diagnosis so the first negative run remains inspectable.

## Direct executable path

The lower-level executable remains available for controlled testing:

```bash
python3 data/ic-support/benchmarks/nxp-kl25/run_live_model_qualification.py \
  --input-dir /storage/projects/plasma-benchmark/nxp-kl25/pre-ai \
  --output-dir <new-unique-output-directory> \
  --ollama-url http://127.0.0.1:11434
```

Do not substitute a different model, context length, seed, timeout, provider, or Gate-3 workspace while calling the result the same experiment. A changed condition is a different run and must be identified as such.

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
- deterministic cross-Pack physical-page context compaction under model-free CI;
- runtime context-envelope integrity checks under model-free CI;
- operator helper syntax and fail-closed orchestration under non-model CI.

Observed in the first real v2 run but **not admitted as semantic quality**:

- compact context reduced provider input from the v1 86131-token observation to 23237 tokens;
- provider completed with `done_reason=stop`;
- one valid JSON document passed the deterministic semantic contract;
- qualification integrity passed;
- semantic screening failed.

Not admitted merely because the harness executes:

- semantic extraction quality;
- model quality;
- canonical dataset;
- HIL;
- production programming;
- destructive security operations.

Repository CI intentionally does not load model weights or claim access to the operator's local Ollama runtime.
