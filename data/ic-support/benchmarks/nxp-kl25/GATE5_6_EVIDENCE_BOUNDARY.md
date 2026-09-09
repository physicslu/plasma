# NXP KL25 Gate 5.6 — Program Longword Evidence Boundary Correction

Target: `MKL25Z128VLK4`

## Objective

Gate 5.6 corrects one deterministic manufacturer-evidence boundary defect. It
does not tune the model, change the source lock, widen unrelated units, or admit
semantic/canonical/HIL/production behavior.

The retained Gate 5.4A run:

```text
/storage/projects/plasma-benchmark/nxp-kl25/runs/20260909T022843Z
```

completed normally (`done_reason=stop`) with complete JSON, eight unit results and
105 facts, but deterministic parsing rejected fact
`nxp-kl25-program-longword-v0-010` because it cited
`nxp_kl25_rm_rev3:p446` while the historical Program Longword Evidence Unit ended
at p445.

That rejection remains valid for the historical run and must not be repaired in
place.

## Manufacturer boundary finding

The locked programming authority remains:

```text
source_id   = nxp_kl25_rm_rev3
document    = KL25P80M48SF0RM Rev. 3
sha256      = 7911a7d9f8192fa317960feabc9377d0fd81a9b90d31f8070cae9612cb237241
byte_length = 6637765
```

The reviewed correction is narrow:

```text
Evidence Unit: nxp-kl25-program-longword-v0
old range:     444–445
new range:     444–446
```

Physical PDF page 445 ends Table 27-36 with a continuation. Physical PDF page
446 begins with the continued Program Longword verify-error/MGSTAT0 row before
section 27.4.10.5 Erase Flash Sector Command. Therefore p446 belongs to both the
Program Longword logical section boundary and the Erase Flash Sector physical
page range. Physical-page overlap is valid; unit identity remains logical and
section based.

No evidence is added beyond p446. In particular, p447 remains outside the Program
Longword Evidence Unit.

## Release identity and historical immutability

The active definitions keep the existing logical definition-set ID but record a
content-addressed boundary release:

```text
release_id = nxp-kl25-evidence-boundary-release-v1
supersedes_definition_digest = 4628dae6b4a0bdad07eff76032df82c1f7f0720d6164abb87f81e4bec502e693
```

The ID is not used as the sole revision identity. Canonical JSON digests bind the
actual definitions and applicability binding used to build Evidence Packs.

Before changing the active files, Gate 5.6 archived the exact historical inputs:

```text
reviewed-evidence-unit-definitions-v0.json
applicability-binding-v0.json
```

`retained-evidence-pack-build.json` is not modified. Its historical definition,
binding, bundle, manifest, pack, evidence and context digests remain evidence of
the Gate 3 release that actually generated prior semantic runs.

## Deterministic applicability regeneration

`derive_applicability_binding.py` remains unchanged. The current
`applicability-binding.json` is regenerated from the corrected reviewed Evidence
Unit definition plus the existing reviewed applicability claims and retained
applicability evidence lock.

Only the Program Longword binding range changes from 444–445 to 444–446. Scope
bridge status, all eight BOUND decisions, required claims, exclusions and all
non-Program-Longword unit bindings remain unchanged.

This is important: Gate 5.6 is not a hand-edited permission to cite p446. The
active binding must equal the deterministic derivation from the active reviewed
inputs.

## Evidence Pack behavior

`build_evidence_pack.py` and `evidence-pack-contract.json` remain unchanged.
The dependency graph remains:

```text
Program Longword
  -> FTFA command sequencing
      -> FTFA register model
```

A newly built Program Longword pack must therefore contain its dependency pages
plus primary pages 444, 445 and 446. The primary unit owns p446 in that pack.
The Erase Flash Sector pack independently owns p446 for its own primary section.
This overlap is deterministic and does not merge the two logical units.

The builder must continue to reject missing pages, source-lock mismatch, content
digest mismatch, applicability mismatch, dependency errors and any unadmitted
state.

## Gate 5.5 interaction

Gate 5.5 remains `mock_only`. Its bounded-extraction architecture is not promoted
to a live provider path by Gate 5.6.

The previous acceptance blocker:

```text
program-longword-table-27-36-continuation
```

is resolved by this evidence release. Model-free bounded extraction now requires:

```text
Program Longword p446 = allowed
Program Longword p447 = rejected
known_acceptance_blockers = []
```

`INTEGRITY_PASS` still means structural aggregation only. It is not semantic
correctness and is not `QUALIFIED`.

## Validation

Gate 5.6 validation is deliberately model-free before any future inference.
Repository CI verifies:

- historical Gate 3 retained provenance still hashes against archived v0 inputs;
- the active release contains exactly one Evidence Unit boundary change;
- all unrelated Evidence Unit definitions are byte-for-byte equivalent at the
  structured-field level;
- the active applicability binding is exactly reproduced by
  `derive_applicability_binding.py`;
- synthetic Program Longword packs contain p446 and exclude p447;
- p446 remains independently attributable to Program Longword and Erase Flash
  Sector in their respective packs;
- source-lock digest and byte length remain frozen;
- semantic/canonical/HIL/production/destructive-security admissions remain false;
- Gate 5.5 bounded extraction remains mock-only and fail-closed.

A one-shot Gate 5.6 GitHub workflow additionally acquires the exact source-locked
Reference Manual, verifies byte length/SHA-256/PDF identity, runs the unchanged
Evidence Pack builder through pre-AI assembly, checks the real Program Longword
p446 boundary, and uploads metadata only. No manufacturer text or model output is
retained in the repository artifact.

## Acceptance and next boundary

Gate 5.6 is complete only when:

```text
model-free repository CI         PASS
real source-lock validation      PASS
corrected Program Longword pack  includes p446, excludes p447
new retained metadata            bound to corrected inputs
old retained metadata/runs       unchanged
Local AI                         NOT EXECUTED
```

After that, Gate 5.6 can be presented for Gate 2 Merge Approval.

A future semantic re-run is a separate scope decision because the new Evidence
Pack/bundle/pre-AI digests constitute a new experiment. Gate 5.6 itself does not
run Ollama/Qwen and does not issue semantic, model-quality, canonical, HIL,
production, or destructive-security admission.
