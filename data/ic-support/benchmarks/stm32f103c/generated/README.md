# Generated benchmark candidates

Harness/AI output belongs here only as a **candidate**, never as ground truth.

## Two benchmark layers

The STM32F103C pilot now separates two questions that were previously mixed:

1. **Blind extraction** — can an isolated extractor recover facts and reuse relationships from the locked official sources?
   - answer key: `../extraction-ground-truth.json`
   - allowed shape only: `../extraction-observed.schema.json`
   - Plasma-internal Profile IDs are deliberately not scored.
2. **Normalization/profile binding** — does Plasma's canonical profile model resolve to the intended reusable Profile IDs?
   - answer key: `../ground-truth.json`
   - checked-in profiles/bindings are part of this later layer.

An extractor cannot infer strings such as Plasma Profile IDs from ST documentation, so they must not be part of a blind-source score.

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
