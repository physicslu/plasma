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
  -> deterministic candidate discovery
  -> reviewed Evidence Unit Catalog
  -> Evidence Packs
  -> evidence-backed Applicability Binding
  -> TargetEvidenceBundle
  -> AI manufacturer-near semantic extraction
  -> deterministic canonicalization / relationship derivation
```

## Current status

The two manufacturer PDFs are source-locked. Discovery is intentionally split into two stages:

1. deterministic candidate discovery based on source-locked bytes and explicit search terms;
2. reviewed Evidence Unit retention before any Evidence Pack admission.

Candidate hits are navigation aids only. They are not proof of applicability or programming semantics.

A first SWPC discovery run exposed a useful regression: generic `Kinetis KL25` / `KL25 Sub-Family` document headers caused `DEVICE_IDENTITY` to match every page. The identity rule was tightened to discriminating commercial/device expressions (`MKL25Z128VLK4`, `MKL25Z128`) and generic family headers are now explicitly forbidden as identity evidence.

All downstream admissions remain false:

- Evidence Pack admission
- semantic extraction admission
- canonical dataset admission
- HIL admission
- production admission
- destructive security operation admission
