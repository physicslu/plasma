# NXP KL25 Live Model Qualification

Target: `MKL25Z128VLK4`

This document defines the bounded live-model experiment that follows the admitted model-free semantic runner CI.

## Qualification objective

The experiment evaluates one exact local-model runtime against the already admitted KL25 Evidence Pack / TargetEvidenceBundle input. It does not rediscover source identity, applicability, or Evidence Pack membership.

The current qualification pipeline is:

```text
retained Gate 3 Evidence Pack workspace
  -> validate exact target/bundle/pre-AI digests
  -> build inference-only compact manufacturer context
     by exact physical-page identity
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

## Frozen experiment v2 — Gate 5.2

`live-model-qualification-contract.json` freezes:

- contract ID: `nxp-kl25-live-model-qualification-v2`;
- exact target: `MKL25Z128VLK4`;
- exact Gate 3 target-bundle and pre-AI manifest digests;
- semantic extraction contract ID;
- transport: `ollama_native_chat`;
- model: `qwen3.8:27b-mlx`;
- runtime label: `kl25-live-model-qualification`;
- context strategy: `cross_pack_physical_page_dedup_v1`;
- context: 65536 tokens;
- maximum output: 8192 tokens;
- temperature: 0.0;
- seed: 0;
- timeout: 1800 seconds;
- output protocol: Ollama `format=<JSON Schema>` structured output;
- exactly one final JSON document; reasoning / `<think>` content is forbidden in the answer channel.

The 64K context setting is consistent with the prior STM32F103C retained Qwen benchmark configuration. Gate 5.2 does not claim that the KL25 run succeeds merely because the runtime envelope is larger; the exact provider token counts remain part of qualification integrity.

## Gate 3 remains immutable

Gate 5.2 does not rebuild or rewrite the admitted Gate 3 Evidence Packs, evidence payloads, `target-bundle.json`, `pre-ai-input.json`, or their retained digests.

The compaction is an inference-only deterministic transformation:

```text
Gate 3 pack materialization
        |
        | validate every retained evidence payload and page digest
        v
(source_id, pdf_page_number, page_text_sha256)
        |
        | remove only identical cross-pack physical-page occurrences
        v
compact manufacturer context
```

A repeated source/page identity with a different SHA-256 or different materialized body is an integrity failure. No manufacturer text is summarized, rewritten, or removed except exact repeated physical-page occurrences.

Per-unit allowed-citation membership remains authoritative in the deterministic semantic parser. Seeing one physical page in the compact context does not authorize every Evidence Unit to cite that page.

## Context-audit evidence that motivated v2

The first real v1 run exposed that the monolithic prompt was dominated by repeated dependency-closure pages:

```text
page occurrences           = 127
unique physical pages      = 33
duplicate occurrences      = 94
occurrence redundancy      = 74.02%
current context bytes      = 413754
compact context bytes      = 107285
context byte reduction     = 74.07%
current prompt bytes       = 419030
compact prompt bytes       = 112561
prompt byte reduction      = 73.14%
provider input tokens      = 86131
estimated compact tokens   = ~23137 (byte-ratio estimate only)
```

The estimate is not a qualification result. The next real v2 run must record authoritative provider `input_tokens` and prove that the actual runtime envelope is respected.

## Negative live-run history

### v0 — prompt-only JSON contract

The first actual `qwen3.8:27b-mlx` run reached the model but returned one complete JSON document followed by a `</think>` marker and a second truncated JSON document. It also used string citations such as `nxp_kl25_rm_rev3:p150` instead of the required evidence-object representation.

Observed root failure:

```text
model_output_invalid_json
```

This run remains negative evidence and must not be repaired by stripping markers, selecting one JSON object, or rewriting citations.

### v1 — structured output, 32K / 4096

Gate 5.1 added provider-side JSON Schema structured output and retained provider metadata before semantic parsing. The next real run eliminated the v0 thinking/duplicate-answer behavior but terminated at the exact output ceiling:

```text
has_think_marker    = false
provider_done       = true
provider_done_reason= length
provider_input_tokens = 86131
provider_generation_tokens = 4096
semantic            = error
qualification       = REJECTED_INTEGRITY
```

The JSON ended with an unterminated string because generation hit `max_tokens=4096`. This result is evidence of an undersized output envelope plus a context-assembly redundancy defect; it is not evidence that KL25 semantic facts are wrong.

Gate 5.2 therefore compacts exact duplicate evidence pages and freezes a 64K / 8192 runtime envelope instead of rerunning the same failed v1 conditions.

## Structured output and citation shape

The provider-facing JSON Schema constrains representation shape, including evidence citations such as:

```json
{
  "source_id": "nxp_kl25_rm_rev3",
  "pdf_page_number": 150
}
```

Provider-side structured decoding is not a trust boundary. The deterministic parser still owns exact unit coverage, FACTS/UNKNOWN semantics, fact-kind validation, exact citation membership in each Evidence Pack, and fail-closed behavior.

## Runtime context integrity

A successful v2 integrity check requires all of the following:

- semantic-run context strategy equals `cross_pack_physical_page_dedup_v1`;
- Gate 3 artifacts are recorded as unmodified;
- context SHA-256 and byte count are retained;
- legacy and compact byte counts are retained;
- page occurrence, unique-page, and duplicate-removal counts are internally consistent;
- cross-pack duplicate removal actually occurred for this KL25 workspace;
- provenance binds the same context digest/statistics as the semantic run;
- provider `input_tokens` is below requested `num_ctx`;
- provider `input_tokens + generation_tokens` fits within requested `num_ctx`;
- `done_reason` is allowed by the frozen contract.

These are runtime-integrity assertions, not semantic-quality assertions.

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

The Mac owns the local Ollama/model runtime. SWPC reaches it through the established SSH reverse tunnel, so qualification still connects only to:

```text
http://127.0.0.1:11434
```

Do not copy the canonical benchmark workspace to the Mac and do not expose Ollama directly on a LAN address for this path.

## Deterministic screening

After integrity passes, the live output must satisfy qualification-specific screening:

- all eight primary Evidence Units return `FACTS` rather than `UNKNOWN`;
- each unit contains at least one fact;
- each unit cites at least one physical page belonging to its primary Evidence Unit, not dependency pages only;
- key NXP-native concepts required for each unit are present;
- STM32-specific projection terms such as `FLASH_CR` and `KEYR` are rejected;
- `raw-response.txt` reparses to exactly the same JSON object retained in `semantic-run.json`.

These checks detect obvious omission, ontology contamination, citation misuse, runtime drift, and artifact tampering. They do not prove every free-text statement is technically correct.

## Manufacturer-evidence review

A run that passes deterministic integrity and semantic screening becomes `READY_FOR_REVIEW`, not `QUALIFIED`.

Final qualification requires an exact per-unit reviewed verdict bound to the semantic-run digest. The review basis must be bounded manufacturer evidence. All eight unit verdicts must be `PASS` for the overall verdict to be `PASS`.

The review must challenge, at minimum:

- whether every material statement is supported by the cited NXP pages;
- whether command prerequisites and completion/error semantics are preserved;
- whether security and mass-erase constraints are stated without widening applicability;
- whether debug/security behavior distinguishes normal SWD access from secure-state MDM-AP recovery behavior;
- whether any cross-vendor or synthesized identity concept entered the output.

Model agreement is not a substitute for evidence review.

## SWPC operator helper

Repeated operator steps are consolidated in one repository helper:

```bash
bash scripts/ic-support-kl25-live.sh status
bash scripts/ic-support-kl25-live.sh context-audit
bash scripts/ic-support-kl25-live.sh build
bash scripts/ic-support-kl25-live.sh run
bash scripts/ic-support-kl25-live.sh diagnose
```

`status` validates the exact pre-AI workspace, prints the frozen v2 context/output envelope, and verifies the loopback Ollama endpoint, exact model ID, and model digest.

`context-audit` is model-free and read-only. It verifies exact cross-pack page identity and reports legacy/compact context and prompt byte counts without contacting Ollama.

`build` rebuilds Gate 3 from source-locked PDFs. Gate 5.2 does not require a rebuild when the retained Gate 3 digests already match the qualification contract.

`run` writes every attempt to a new UTC run directory:

```text
/storage/projects/plasma-benchmark/nxp-kl25/runs/<UTC-run-id>/
```

Failed runs are retained and never rewritten into passing artifacts.

`diagnose` is read-only. It reports JSON status, semantic error class, compact-context statistics, requested `num_ctx` / `max_tokens`, provider token usage, completion reason, and qualification integrity errors.

## Expected successful pre-review state

```text
semantic=success
qualification=READY_FOR_REVIEW
```

`QUALIFIED` still requires a separate manufacturer-evidence review bound to the exact `semantic_run_digest`.

## Trust boundary

Admitted by model-free CI after this harness change:

- deterministic cross-pack physical-page compaction logic;
- fail-closed duplicate identity/hash validation;
- structured-output schema and transport request construction;
- 64K / 8192 frozen wiring under mocked transport;
- context/provenance/runtime-envelope integrity checks;
- operator helper syntax and model-free context audit.

Not admitted merely because CI passes:

- a successful real v2 local-model run;
- semantic extraction quality;
- canonical dataset;
- HIL;
- production programming;
- destructive security operations.

Repository CI intentionally does not load model weights or claim access to the operator's local Ollama runtime.
