# NXP KL25 Cross-Vendor Evidence Foundation

Target: `MKL25Z128VLK4`

This benchmark exists to test whether the Plasma IC Evidence pipeline is genuinely cross-vendor rather than a STM32-specific model with renamed fields.

## Manufacturer sources

- Data sheet: `KL25P80M48SF0`, Rev. 5.
- Reference manual: `KL25P80M48SF0RM`, Rev. 3.

For KL25, the Reference Manual fills the **programming authority** role. Plasma does not require the vendor document to be literally named `Programming Manual`.

## Cross-vendor boundary

The pipeline must preserve the NXP flash command-engine model as manufacturer-near facts. It must not project STM32-specific `KEYR`, `CR`, `PER`, `MER`, or `PG` concepts into NXP evidence merely to fit the existing benchmark.

Expected architecture:

```text
locked manufacturer bytes
  -> deterministic preprocessing
  -> evidence unit catalog
  -> Evidence Packs
  -> evidence-backed Applicability Binding
  -> TargetEvidenceBundle
  -> AI manufacturer-near semantic extraction
  -> deterministic canonicalization / relationship derivation
```

## Current foundation status

The source documents have been acquired on the SWPC, but their exact bytes are intentionally not guessed by repository automation. `capture_source_lock.py` must be run against the local PDF directory to generate the real SHA-256/byte-length source lock.

Until that source lock and deterministic evidence units are retained, all of the following remain denied:

- Evidence Pack admission
- semantic extraction admission
- canonical dataset admission
- HIL admission
- production admission
- destructive security operation admission

## SWPC integrity capture

After this branch is available on SWPC:

```bash
python3 data/ic-support/benchmarks/nxp-kl25/capture_source_lock.py \
  --source-dir /storage/projects/plasma-benchmark/nxp-kl25/source \
  --output /tmp/nxp-kl25-source-lock.json
```

The generated file contains only document identity metadata, SHA-256 digests, and byte lengths. It does not copy PDF contents into the repository.
