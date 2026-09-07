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
  -> deterministic Evidence Pack / TargetEvidenceBundle   [ADMITTED]
  -> pre-AI input manifest / model-context assembly       [ADMITTED]
  -> AI manufacturer-near semantic extraction             [not admitted]
  -> deterministic canonicalization                       [not admitted]
```

AI does not own exact commercial identity, manufacturer-document membership, target applicability, applicability exclusions, Evidence Unit dependency closure, or deterministic pack membership.

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

The retained applicability run was regenerated from source-locked DS/RM bytes using `pdftotext -layout -enc UTF-8`. Its evidence/provenance is retained in `retained-applicability-evidence-lock.json` and `reviewed-applicability-claims.json`.

The target scope bridge is admitted:

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

`derive_applicability_binding.py` derives all eight reviewed units as `BOUND` for `MKL25Z128VLK4`. Missing prerequisites derive `UNKNOWN`; malformed or provenance-mismatched retained evidence is rejected.

## Gate 3 Evidence Pack model

`build_evidence_pack.py` defines one primary Evidence Pack for each admitted Evidence Unit and computes deterministic transitive dependency closure before materializing manufacturer text.

Examples:

```text
Program Longword
  -> FTFA command sequencing
      -> FTFA register model

Debug / Security interaction
  -> SWD / MDM-AP
  -> Flash Security
      -> FTFA command sequencing
          -> FTFA register model
```

This is intentionally stronger than copying only the primary operation pages. The objective is to provide the smallest context that still preserves the register/status/sequence/security dependencies required to interpret the primary Evidence Unit.

Each pack identity is bound to:

- exact source-lock fingerprint;
- Evidence Unit definition-set digest;
- Applicability Binding digest;
- Evidence Pack contract digest;
- builder SHA-256;
- included unit set and dependency origin;
- physical PDF page numbers;
- normalized page-text SHA-256 values.

The target bundle contains the eight pack digests for exact target `MKL25Z128VLK4`. Manufacturer text is materialized for execution but is not committed to Git as a retained artifact.

## Retained Gate 3 live-source proof

After offline CI passed, the admitted contract was rerun against the exact source-locked NXP Reference Manual. The live run verified the RM byte length/SHA-256, executed the pinned PDF-to-text transform, built all eight real packs, assembled the target bundle and pre-AI context, and retained metadata only.

Final retained provenance is in `retained-evidence-pack-build.json`:

```text
workflow run     34111376564
artifact id      10014477883
generation head  0eb876d7699f55edcbf493c86c2ce6d593ffb94e
bundle digest    628aa2c7664cdf9778a11e56a8da0a9cf8816aaec704baf893bfae5a9fba0244
pack count       8
```

The retained artifact did not contain manufacturer text and did not execute semantic extraction. Repository regression validates that this retained proof remains bound to the current source-lock, definition set, applicability binding, Evidence Pack contract and builder SHA.

## Pre-AI CI strategy

Normal repository CI is intentionally **model-free and network-free** for this stage. It uses synthetic page fixtures to test every deterministic and orchestration path that can be proven without real model inference:

```text
contract validation
  -> dependency graph validation
  -> dependency closure
  -> pack construction
  -> page deduplication
  -> page-content digest validation
  -> TargetEvidenceBundle assembly
  -> pre-AI input manifest
  -> model-context assembly
  -> retained-provenance validation
  -> fail-closed mutation tests
  -> STOP before model inference
```

The permanent CI therefore does not require Ollama, oMLX, model weights, an API key, NXP website availability, or semantic inference.

The one-shot live-source workflow used during Gate 3 is removed after retaining the proof so routine CI is not coupled to external website availability.

When a real KL25 model runner is introduced in the next gate, its transport/orchestration behavior should also be covered by deterministic mocked CI (success, timeout, malformed JSON, schema rejection and runner errors). Actual model-weight inference and semantic-quality scoring remain separate live/model benchmarks.

## Gate 3 fail-closed requirements

Evidence Pack construction rejects or invalidates the build when any of these conditions occurs:

- target scope bridge is not `BOUND`;
- any required unit binding is `UNKNOWN`;
- applicability exclusions are not reviewed;
- catalog/binding/source-lock identities disagree;
- dependency graph contains unknown nodes, self-dependencies or cycles;
- a required physical PDF page is absent;
- source bytes fail byte-length or SHA-256 verification;
- materialized page content differs from the recorded page hash;
- pack/bundle/evidence digests differ from the pre-AI manifest;
- retained live-source provenance no longer matches deterministic repository inputs.

No test may convert an unknown or malformed state into an inferred `BOUND` state.

## Current trust boundary

Admitted for this benchmark evidence pipeline:

- source lock;
- deterministic preprocessing/discovery;
- reviewed Evidence Unit Catalog;
- reviewed target scope bridge;
- deterministic Applicability Binding;
- deterministic Evidence Pack;
- exact-target `TargetEvidenceBundle`;
- pre-AI CI through deterministic model-context assembly.

The following remain explicitly denied:

- semantic extraction admission;
- canonical dataset admission;
- HIL admission;
- production admission;
- destructive security operation admission.

Evidence Pack / pre-AI admission proves deterministic evidence packaging and pre-inference input integrity. It does **not** prove that any LLM extracts the correct semantics, that OpenOCD can program the device, or that hardware erase/program/security operations are safe.
