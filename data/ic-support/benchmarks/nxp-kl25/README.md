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

## Retained source lock

The exact SWPC-downloaded PDF identities are retained in `source-lock.json`:

```text
nxp_kl25_ds_rev5
sha256 e42271b7f612ac1b0812001e62bef10d217be4a61dbee5bb0a1e5c4076209a3b
bytes  1280088

nxp_kl25_rm_rev3
sha256 7911a7d9f8192fa317960feabc9377d0fd81a9b90d31f8070cae9612cb237241
bytes  6637765
```

The retained RM artifact was independently sanity-checked on SWPC as PDF 1.6 with 807 pages. A prior 10-byte failed download was rejected and is not part of the source lock.

`capture_source_lock.py` now fails closed for implausibly small artifacts and files without a `%PDF-` header.

## Current admission status

Source identity is locked. Deterministic evidence-unit discovery has not yet been retained, so all of the following remain denied:

- Evidence Pack admission
- semantic extraction admission
- canonical dataset admission
- HIL admission
- production admission
- destructive security operation admission

## Reproduce SWPC integrity capture

```bash
python3 data/ic-support/benchmarks/nxp-kl25/capture_source_lock.py \
  --source-dir /storage/projects/plasma-benchmark/nxp-kl25/source \
  --output /tmp/nxp-kl25-source-lock.json
```

The generated file contains only document identity metadata, SHA-256 digests, and byte lengths. It does not copy PDF contents into the repository.
