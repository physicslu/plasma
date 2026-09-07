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
  -> candidate discovery
  -> reviewed candidate boundary
  -> heading-aware Evidence Unit construction candidates
  -> reviewed Evidence Unit Catalog
  -> Evidence Packs
  -> evidence-backed Applicability Binding
  -> TargetEvidenceBundle
  -> AI manufacturer-near semantic extraction
  -> deterministic canonicalization / relationship derivation
```

## Current retained source lock

- `nxp_kl25_ds_rev5`: SHA-256 `e42271b7f612ac1b0812001e62bef10d217be4a61dbee5bb0a1e5c4076209a3b`, 1,280,088 bytes.
- `nxp_kl25_rm_rev3`: SHA-256 `7911a7d9f8192fa317960feabc9377d0fd81a9b90d31f8070cae9612cb237241`, 6,637,765 bytes.

The capture path fails closed for implausibly small or non-PDF artifacts.

## Deterministic discovery result

The first SWPC run produced 864 candidate pages because generic family headers polluted `DEVICE_IDENTITY`. The identity policy was tightened to commercial/device expressions only.

The second run produced 129 candidate pages. Cluster review retained these candidate boundaries:

- Reference Manual pages 419-456: `flash_programming_core_candidate`.
- Reference Manual pages 149-157: `debug_security_recovery_candidate`.
- Data Sheet candidate pages remain individually reviewable context and are not automatically admitted.

Keyword hits remain navigation evidence only. They are not semantic authority.

## Evidence Unit construction

`build_evidence_unit_candidates.py` operates only on reviewed candidate boundaries. It verifies the locked PDF bytes, reproduces the same `pdftotext -layout -enc UTF-8` preprocessing, records per-page text hashes, detects heading candidates, and preserves NXP-native category hits.

The generated artifact is an **Evidence Unit construction candidate catalog**, not an admitted Evidence Unit Catalog. Section boundaries must be reviewed from document structure before Evidence Unit admission.

## Trust boundary

The following remain denied:

- Evidence Unit Catalog admission
- Evidence Pack admission
- semantic extraction admission
- canonical dataset admission
- HIL admission
- production admission
- destructive security operation admission
