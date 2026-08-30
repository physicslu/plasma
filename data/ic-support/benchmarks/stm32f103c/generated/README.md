# Generated benchmark candidates

Harness/AI output belongs here only as a **candidate**, never as ground truth.

Candidate format:

```json
{
  "observed": {
    "...": "same projection shape as ground-truth.json -> expected"
  }
}
```

Validate a candidate with:

```bash
python data/ic-support/compare_benchmark.py --candidate path/to/candidate.json
```

The checked-in `ground-truth.json` is independently evidence-backed. Do not generate or overwrite it from the same extraction run being evaluated.
