# Generated benchmark candidates

Harness/AI output belongs here only as a **candidate**, never as ground truth.

## Grounded manual experiments

Files named `*.raw.json` are retained AI outputs from controlled manual experiments. They are evidence of what a model actually produced and must not be edited to make them satisfy a benchmark contract.

`qwen3.8-27b-mlx-grounded-run1.raw.json` is a Qwen 3.8 27B MLX result produced with DS5319 Rev 20 and PM0075 Rev 2 supplied to the model. It did **not** consume the complete `source-lock.json` input set because the locked Plasma STM32F1 catalog blob was not provided. Therefore it is useful as a manufacturer-grounded A/B experiment, but it is **not** an official source-locked blind candidate and must not be renamed to `candidate.json` or reported as a formal benchmark PASS.

## Review and handover records

Later programming-profile decomposition and executable-style pseudocode experiments are reviewed separately from immutable raw model evidence. Review notes are not answer keys and are not inputs to a blind model run.

- [Qwen 3.8 27B MLX programming-decomposition review](../reviews/qwen3.8-27b-mlx-programming-decomposition-review.md) records known corrections, unresolved failure modes, and candidate semantic-validator invariants.
- [IC Support Local-AI Benchmark Handover](../../../../../docs/development/ic-support-ai-benchmark-handover.md) records the current model-role conclusion and the control conditions for the next independent model comparison.

Do not expose these review records to a model during an independent blind comparison, because they contain known failure classes and corrected representations.

## Three benchmark questions

The STM32F103C pilot keeps three questions separate:

1. **Blind extraction** — can an isolated extractor recover facts and reuse relationships from the locked official sources?
   - answer key: `../extraction-ground-truth.json`
   - allowed shape only: `../extraction-observed.schema.json`
   - Plasma-internal Profile IDs are deliberately not scored.
2. **Normalization/profile binding** — does Plasma's canonical profile model resolve to the intended reusable Profile IDs?
   - answer key: `../ground-truth.json`
   - checked-in profiles/bindings are part of this later layer.
3. **Manufacturer-only Full-vs-Pack A/B** — can deterministic DS5319 reduction lower context cost without reducing engineering correctness?
   - contract: `../evidence-pack-benchmark-v0.json`
   - full arm: exact locked DS5319 + exact locked PM0075.
   - reduced arm: deterministic DS5319 Evidence Pack + exact locked PM0075.
   - the model/runtime/prompt/source revisions and `pdftotext` fingerprint are controlled variables.

An extractor cannot infer strings such as Plasma Profile IDs from ST documentation, so they must not be part of a blind-source score.

## Full-vs-Pack preparation

Materialize the exact locked DS5319 PDF, then build the semantic Evidence Pack **outside** the Plasma repository:

```bash
python data/ic-support/evidence-pack/semantic_pack.py \
  --source-lock data/ic-support/benchmarks/stm32f103c/source-lock.json \
  --policy data/ic-support/evidence-pack/policies/st-ds5319-rev20-programming-v0.json \
  --pdf /outside/repo/st_ds5319_rev20.pdf \
  --output-dir /outside/repo/ds5319-pack
```

The generated `evidence.txt` is the reduced datasheet context. `structure.json`, `catalog.json`, `pack.json`, `binding.json`, and the C8/CB target bundles retain the exact source/tool/policy identities needed to audit that context. These manufacturer-content-derived outputs are not checked into Git.

The A/B experiment is not the formal blind benchmark. Do not inject the Plasma catalog blob into the manufacturer-only A/B arms merely to make their source sets resemble the formal benchmark.

## Blind workspace

Prepare the benchmark outside the Plasma repository:

```bash
python data/ic-support/benchmarks/stm32f103c/prepare_blind_workspace.py prepare \
  /tmp/plasma-stm32f103c-blind
```

The command:

- downloads the exact source-locked ST PDFs;
- verifies SHA-256 and byte length;
- materializes the exact locked catalog Git blob;
- produces searchable `pdftotext -layout` text from the verified PDFs;
- copies only the source lock, extraction contract, and answer-free observed schema;
- refuses a workspace inside the Plasma repository;
- initializes the isolated directory as its own Git repository.

`curl`, `git`, and `pdftotext` must already be installed. The helper does not install packages.

Then launch a **fresh** Harness session from the isolated workspace:

```bash
python data/ic-support/benchmarks/stm32f103c/prepare_blind_workspace.py harness \
  /tmp/plasma-stm32f103c-blind
```

Read that workspace's `PROMPT.md`. The normal `scripts/local-ai-harness harness` command is intentionally **not** used for this benchmark because it starts Harness from the Plasma repository root.

The workspace isolation is operational, not an OS sandbox. `workspace-manifest.json` records that limitation explicitly. Do not claim stronger isolation than was actually enforced.

## Candidate contract

A candidate must follow `../extraction-contract.json` and use schema version `0.2.0`:

```json
{
  "schema_version": "0.2.0",
  "benchmark_id": "stm32f103c-profile-decomposition-v0",
  "source_lock_id": "stm32f103c-source-lock-v0",
  "source_digests": {
    "st_ds5319_rev20": "sha256:<locked digest>",
    "st_pm0075_rev2": "sha256:<locked digest>",
    "plasma_stm32f1_catalog_main": "git_blob_sha1:<locked digest>"
  },
  "extractor": {
    "name": "<actual Harness/model identity>",
    "version": "<model/prompt/workflow version>"
  },
  "observed": {
    "...": "must satisfy extraction-observed.schema.json"
  }
}
```

For evidence that is not present in the locked inputs, emit `null` or `unknown` where the schema permits it. Do not guess.

Save the result as `candidate.json` in the isolated workspace and evaluate it from the Plasma checkout:

```bash
python data/ic-support/benchmarks/stm32f103c/prepare_blind_workspace.py validate \
  /tmp/plasma-stm32f103c-blind
```

The evaluator is allowed to read `extraction-ground-truth.json`; the extraction run is not.

`ground-truth.json`, `extraction-ground-truth.json`, checked-in profiles, and checked-in bindings are all forbidden inputs to the blind extraction session.
