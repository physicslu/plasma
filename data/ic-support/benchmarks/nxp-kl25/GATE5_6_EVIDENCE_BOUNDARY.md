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

A one-shot Gate 5.6 GitHub workflow additionally acquired the exact source-locked
Reference Manual, verified byte length/SHA-256/PDF identity, ran the unchanged
Evidence Pack builder through pre-AI assembly, checked the real Program Longword
p446 boundary, and uploaded metadata only. No manufacturer text or model output
was retained in the repository artifact.

## Retained Gate 5.6 live-source proof

The corrected real-source build completed successfully and is retained in
`retained-evidence-pack-build-v1.json`.

```text
workflow run       34312404077
artifact id        10088834705
artifact digest    sha256:3e70c60cd728d41ed372bbad436fe5c5d677a80cd930b45dd21f76e0a704692a
generation head    95e631424a42f4a5a22da555eed9f68dda2a4a8f
source SHA-256      7911a7d9f8192fa317960feabc9377d0fd81a9b90d31f8070cae9612cb237241
definition digest  c9c2ed86a0aa5ccdcc1861a0153d0b79cc94f57a568faa5432d9f0389bb4132f
binding digest     1e88d2bb1cfdae65e6456bca3407d2419a7b2bd391729fd2feae1917ac4be038
contract digest    6d5e004a5fac4881cb19f99e921f9afb63f23dcc5aa90b329a7651cda5dcea2c
builder SHA-256    b4e49286c3bab6d8cd4a6d873e272ecefa31106bdcd1aede86459849420ab611
bundle digest      ffe9bfaa8a6ed47c8edd6d952fe1ca2cc114513c2a1f0832892ab9484e7322bf
manifest digest    03155ede421cddb7c2ab64e079ef43b1124a7c78cbedf1e7a08c60c29796bb6e
model-context SHA  8ebeab88b4a1e6c540c8af2d4d1941bdb02f0d31389f92a1d4bc0366103cfaaa
pack count         8
```

The Program Longword real-source pack digest is:

```text
d8972697fca92045158a6bcd4d868a46a13b100b96ef86ffc273781aceb53ffe
```

Its primary range is exactly 444–446. Its page reference for p446 is bound to
`nxp-kl25-program-longword-v0`, and p447 is absent. The p446 normalized page-text
SHA-256 is:

```text
5437e789dd3e27e2d4db9870209c0013ab6f5550f6f41a19ff2e4135c55488fd
```

Only the Program Longword evidence-text digest changed relative to the historical
v0 retained build. All other unit evidence-text digests are unchanged. All pack
digests change because every pack cryptographically binds the active definition
and applicability-binding digests.

This new proof is a new evidence release, not a mutation of the old proof. The
historical bundle `628aa2c7...` and manifest `b26621b1...` remain the authority
for the old semantic runs; the corrected bundle `ffe9bfaa...` and manifest
`03155ede...` are the authority for any future experiment that explicitly adopts
Gate 5.6.

## Acceptance and next boundary

Gate 5.6 acceptance is:

```text
model-free repository CI         PASS required at final revision
real source-lock validation      PASS
corrected Program Longword pack  includes p446, excludes p447
new retained metadata            bound to corrected inputs
old retained metadata/runs       unchanged
Local AI                         NOT EXECUTED
```

After final repository CI is green, Gate 5.6 can be presented for Gate 2 Merge
Approval.

A future semantic re-run is a separate scope decision because the new Evidence
Pack/bundle/pre-AI digests constitute a new experiment. Gate 5.6 itself does not
run Ollama/Qwen and does not issue semantic, model-quality, canonical, HIL,
production, or destructive-security admission.
