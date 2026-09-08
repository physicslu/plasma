# NXP KL25 Gate 5.2 — Context Compaction Evidence

Status: engineering evidence and experiment rationale. This file contains no manufacturer text.

## Observed v1 runtime evidence

The retained real v1 run under `qwen3.8:27b-mlx` reported:

```text
provider input_tokens      = 86131
provider generation_tokens = 4096
provider done_reason       = length
semantic status            = error
qualification              = REJECTED_INTEGRITY
```

The response no longer contained the v0 thinking marker / duplicate-answer pattern, but it ended in an unterminated JSON string at the output ceiling.

## Read-only structural audit

The retained Gate 3 workspace was audited without model inference and without changing any Gate 3 artifact:

```text
page_occurrences           = 127
unique_physical_pages      = 33
duplicate_occurrences      = 94
occurrence_redundancy_pct  = 74.02
current_context_bytes      = 413754
dedup_context_bytes        = 107285
context_byte_reduction     = 74.07%
current_prompt_bytes       = 419030
dedup_prompt_bytes         = 112561
prompt_byte_reduction      = 73.14%
estimated_dedup_tokens     = 23137
```

`estimated_dedup_tokens` is only a byte-ratio estimate. Provider-reported token counts from the next real run remain authoritative.

## Root cause

Gate 3 intentionally materializes one Evidence Pack per primary Evidence Unit, including deterministic transitive dependency closure. Each pack deduplicates physical pages internally, but the v1 semantic context concatenated all eight complete pack payloads. The same dependency pages were therefore materialized repeatedly across packs.

This is a semantic-execution context-assembly defect, not a Gate 3 evidence defect.

## Gate 5.2 decision

Gate 5.2 keeps all Gate 3 bytes and digests immutable and introduces an inference-only deterministic context transformation:

```text
validated Gate 3 evidence payloads
  -> exact materialized-page framing validation
  -> key by source_id + pdf_page_number + page_text_sha256
  -> fail closed on repeated page identity with different digest/body
  -> materialize each identical physical page once
  -> preserve deterministic per-unit allowed-citation maps in the semantic prompt/parser
```

The v2 runtime envelope is frozen at:

```text
model        = qwen3.8:27b-mlx
num_ctx      = 65536
max_tokens   = 8192
temperature  = 0.0
seed         = 0
structured   = JSON Schema
```

This is a new experiment version. It does not retroactively convert either v0 or v1 into a passing run.

## Admission boundary

CI may admit the deterministic compaction implementation, integrity rules, runtime wiring, and operator tooling without model weights.

CI does not admit:

- a successful real v2 model run;
- semantic factual correctness;
- model quality;
- canonical dataset;
- HIL;
- production programming;
- destructive security operations.
