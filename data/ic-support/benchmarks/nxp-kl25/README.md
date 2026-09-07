# NXP KL25 Cross-Vendor Evidence Foundation

Target: `MKL25Z128VLK4`

This benchmark exists to test whether the Plasma IC Evidence pipeline is genuinely cross-vendor rather than a STM32-specific model with renamed fields.

## Manufacturer sources

- Data sheet: `KL25P80M48SF0`, Rev. 5.
- Reference manual: `KL25P80M48SF0RM`, Rev. 3.

For KL25, the Reference Manual fills the **programming authority** role. Plasma does not require the vendor document to be literally named `Programming Manual`.

## Cross-vendor boundary

The pipeline must preserve the NXP flash command-engine model as manufacturer-near facts. It must not project STM32-specific `KEYR`, `CR`, `PER`, `MER`, or `PG` concepts into NXP evidence merely to fit the existing benchmark.

Current architecture:

```text
locked manufacturer bytes
  -> deterministic preprocessing
  -> candidate discovery
  -> reviewed candidate boundary
  -> heading-aware Evidence Unit construction
  -> reviewed Evidence Unit Catalog
  -> reviewed applicability claims
  -> deterministic target scope bridge
  -> deterministic per-unit Applicability Binding
  -> Evidence Pack / TargetEvidenceBundle        [not yet admitted]
  -> AI manufacturer-near semantic extraction    [not yet admitted]
  -> deterministic canonicalization              [not yet admitted]
```

AI does not own exact commercial identity, manufacturer-document membership, target applicability, applicability exclusions, or cross-unit binding.

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

## Evidence Unit Catalog

Eight NXP-native Evidence Units are admitted to the benchmark Evidence Unit Catalog after heading-aware review:

- FTFA register model
- FTFA command sequencing
- Program Longword
- Erase Flash Sector
- Erase All Blocks
- Flash Security
- Debug / Security interaction
- SWD / MDM-AP

Catalog admission means these are reviewed logical manufacturer-section units. It does not by itself prove that the units apply to every KL25 orderable part.

## Reviewed applicability and deterministic binding

The retained applicability run was regenerated from source-locked DS/RM bytes using `pdftotext -layout -enc UTF-8`. The selected anchors are retained in `retained-applicability-evidence-lock.json` and reviewed in `reviewed-applicability-claims.json` with `source_id`, physical PDF page and normalized-page SHA-256.

The target scope bridge is now admitted:

```text
exact MKL25Z128VLK4 identity
  -> exact membership in the locked KL25 Reference Manual
  -> explicit KL25 family/document anchors
```

The absent intermediate expression `MKL25Z128` is intentionally not synthesized. Fuzzy/substring identity equivalence remains forbidden.

Module/interface claims for FTFA, SWD, MDM-AP and the Flash security model are reviewed. Applicability exclusions are also retained, including:

- this device operates only in NVM Normal mode; NVM Special references are not applicable;
- secure state restricts SWD memory/programming access;
- MDM-AP mass erase can be disabled by security configuration;
- commanded Erase All Blocks has protection constraints;
- backdoor unsecure is mode/security/KEYEN/key gated.

`derive_applicability_binding.py` therefore derives all eight reviewed units as `BOUND` for `MKL25Z128VLK4`. Missing prerequisites derive `UNKNOWN`; malformed or provenance-mismatched retained evidence is rejected.

## Current trust boundary

Admitted for this benchmark evidence pipeline:

- source lock
- deterministic preprocessing/discovery
- reviewed Evidence Unit Catalog
- reviewed target scope bridge
- deterministic Applicability Binding

The following remain denied:

- Evidence Pack admission
- semantic extraction admission
- canonical dataset admission
- HIL admission
- production admission
- destructive security operation admission

Applicability binding is evidence governance. It is not proof of executable erase/program/unsecure behavior on real hardware.
