# Generated benchmark candidates

Harness/AI output belongs here only as a **candidate**, never as ground truth.

A valid benchmark run must follow `../extraction-contract.json`: it may consume only the locked source set and target ICPNs. It must not read `ground-truth.json`, checked-in profiles, or checked-in bindings.

Candidate format:

```json
{
  "schema_version": "0.1.0",
  "benchmark_id": "stm32f103c-profile-decomposition-v0",
  "source_lock_id": "stm32f103c-source-lock-v0",
  "source_digests": {
    "st_ds5319_rev20": "sha256:<locked digest>",
    "st_pm0075_rev2": "sha256:<locked digest>",
    "plasma_stm32f1_catalog_main": "git_blob_sha1:<locked digest>"
  },
  "extractor": {
    "name": "<Harness/AI/model identifier>",
    "version": "<workflow/prompt/model version>"
  },
  "observed": {
    "...": "same normalized projection shape as ground-truth.json -> expected"
  }
}
```

Validate a candidate with both metadata and answer-key checks:

```bash
python data/ic-support/benchmarks/stm32f103c/validate_extraction_candidate.py path/to/candidate.json
```

`compare_benchmark.py --candidate` remains useful for raw projection debugging, but it does not by itself prove that the candidate used the correct source bytes or that the run was isolated.

The checked-in `ground-truth.json` is independently evidence-backed and bound to `source-lock.json`. Do not generate, overwrite, or reveal it to the same extraction run being evaluated.
