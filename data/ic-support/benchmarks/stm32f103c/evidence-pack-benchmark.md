# Evidence Pack benchmark note

The STM32F103C Evidence Pack A/B experiment is deliberately separate from the existing formal blind extraction benchmark.

- Formal blind benchmark authority remains `source-lock.json` and its existing extraction contract.
- Manufacturer-only A/B compares the same model/runtime/prompt against:
  - full DS5319 + full PM0075;
  - deterministic DS5319 Evidence Pack + full PM0075.
- The Plasma STM32F1 catalog blob remains part of the formal blind benchmark but is not injected into the manufacturer-only A/B arm merely to make the experiments look identical.
- Generation does not read either answer key. Ground truth is opened only by the separate scoring command after raw model outputs exist.
- Raw model outputs are immutable experiment evidence and should be kept outside Git unless an explicit retained-evidence decision is made.
- Reduced context is acceptable only if engineering correctness does not regress. Performance improvements are secondary evidence, not an admission gate.

## Harness

`ab_benchmark.py` has two generation-side responsibilities:

1. Prepare exact manufacturer-only contexts from the source lock.
2. Execute paired trials against an OpenAI-compatible streaming chat-completions endpoint.

`score_ab_benchmark.py` is a separate scoring-side command. It is the only A/B harness component that reads `extraction-ground-truth.json`.

The model is not told which arm it receives. The prompt template is identical in both arms; only the supplied datasheet context changes.

### 1. Prepare the workspace

Use already-downloaded exact locked PDFs:

```bash
python data/ic-support/benchmarks/stm32f103c/ab_benchmark.py prepare \
  --workspace /tmp/plasma-ab \
  --ds-pdf /path/to/locked-ds5319.pdf \
  --pm-pdf /path/to/locked-pm0075.pdf
```

Or use the existing canonical manufacturer source transport:

```bash
python data/ic-support/benchmarks/stm32f103c/ab_benchmark.py prepare \
  --workspace /tmp/plasma-ab \
  --fetch-sources
```

Preparation verifies the exact source-lock bytes, records the `pdftotext`/normalization fingerprint, materializes full DS/PM text with physical-page markers, and rebuilds the deterministic DS5319 Evidence Pack. Manufacturer source bytes and generated text remain outside Git.

### 2. Run paired trials

```bash
python data/ic-support/benchmarks/stm32f103c/ab_benchmark.py run-pair \
  --workspace /tmp/plasma-ab \
  --results-dir /tmp/plasma-ab-results \
  --base-url http://127.0.0.1:<port>/v1 \
  --model <exact-model-id> \
  --runtime-label <runtime-and-version> \
  --trials 3 \
  --temperature 0 \
  --max-tokens 4096
```

Odd trials run `full -> reduced`; even trials run `reduced -> full`. This balances first-run/warm-cache ordering effects without changing the task prompt.

The endpoint must be OpenAI chat-completions compatible. TTFT is only claimed when streamed content is actually observed. Token counts are accepted only when the runtime reports usage; the harness does not invent tokenizer estimates. Remote peak memory remains `null` unless independently measured by the runtime.

### 3. Score after generation

```bash
python data/ic-support/benchmarks/stm32f103c/score_ab_benchmark.py \
  --results-dir /tmp/plasma-ab-results \
  --output /tmp/plasma-ab-results/score.json
```

The scorer reports:

- exact field-level accuracy;
- wrong asserted fields;
- missing/unknown fields;
- uncited asserted fields;
- out-of-context citations;
- a clearly labeled unsupported-inference proxy;
- input bytes and runtime-reported token counts;
- TTFT and total latency medians across trials.

The unsupported-inference proxy is intentionally conservative: it is the union of wrong asserted fields and asserted fields without any valid in-arm citation. A citation proves that evidence was available to the model; it does **not** mechanically prove that the cited page semantically entails the claim.

## First comparison target

The existing research handover identifies `qwen3.8:27b-mlx` as the strongest current candidate for the IC Knowledge / Specification Agent role. A first Full-vs-Pack measurement should therefore use that exact model/runtime configuration before comparing a second model family, unless the runtime has changed and the change is explicitly recorded.

See `evidence-pack-benchmark-v0.json` for the machine-readable experiment contract.
