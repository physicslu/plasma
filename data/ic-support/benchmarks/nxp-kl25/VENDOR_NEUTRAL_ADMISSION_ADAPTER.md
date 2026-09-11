# NXP KL25 vendor-neutral admission adapter

This adapter projects the immutable NXP KL25 post-review release into the
vendor-neutral admission v1 ABI. It is a deterministic compatibility layer.
The existing NXP validators remain authoritative and always run before the
generic validator.

The adapter is locked to retained Gate 5.7A run `20260909T080946Z`, the final
Gate 5.8 manufacturer review, and immutable release
`dc256318618f20d3d5bffbee8fe74fd0c9554b7b457d448f1bc13ed86f18f987`.
It refuses changed bytes, identities, counts, fact digests, candidate digests,
review bindings, backend locks, or release files.

## Projection

- all 140 reviewed facts become content-addressed fact wrappers;
- the 130 unchanged candidates inherit their exact five-dimension Gate 5.8
  full-PASS verdicts;
- all 13 transformed candidates bind their explicit post-review manufacturer
  reviews;
- the generic candidate review covers the exact 143-candidate set;
- the NXP canonical specification is retained in an opaque vendor payload
  indexed by canonical field path;
- the legacy OpenOCD lock digest and the distinct generic backend lock digest
  are both retained;
- `READ`, `VERIFY`, `PROGRAM`, and request-level `ERASE` are admitted for the
  Software Executor; `ERASE` maps only to the target-owned exact-sector
  `ERASE_SECTOR` contract;
- all destructive and security operations remain blocked;
- every operation keeps `hardware_runtime_ready=false`.

The output is a separate sidecar directory containing
`vendor-neutral-admission-package.json`, `qualification.json`, and
`release-manifest.json`. The legacy release and Gate 5.8 directories are read
only inputs.

## Build and validate

From the repository root on the integration host:

```bash
python data/ic-support/benchmarks/nxp-kl25/vendor_neutral_admission_adapter.py build \
  --run-dir /storage/projects/plasma-benchmark/nxp-kl25/bounded-primary-runs/20260909T080946Z \
  --gate58-dir /storage/projects/plasma-benchmark/nxp-kl25/gate58/20260910T014555Z \
  --legacy-release-dir /storage/projects/plasma-benchmark/nxp-kl25/post-review-disposition/releases/20260910T055202Z-dc256318618f \
  --sidecar-dir /storage/projects/plasma-benchmark/nxp-kl25/vendor-neutral-admission/releases/<new-release-id>

python data/ic-support/benchmarks/nxp-kl25/vendor_neutral_admission_adapter.py validate \
  --run-dir /storage/projects/plasma-benchmark/nxp-kl25/bounded-primary-runs/20260909T080946Z \
  --gate58-dir /storage/projects/plasma-benchmark/nxp-kl25/gate58/20260910T014555Z \
  --legacy-release-dir /storage/projects/plasma-benchmark/nxp-kl25/post-review-disposition/releases/20260910T055202Z-dc256318618f \
  --sidecar-dir /storage/projects/plasma-benchmark/nxp-kl25/vendor-neutral-admission/releases/<new-release-id>
```

This release is Software Executor evidence only. It does not admit HIL,
production catalog/routing, runtime wiring, destructive security workflows, or
physical programming behavior.
