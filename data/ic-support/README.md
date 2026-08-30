# Plasma IC Support — Phase A Pilot

`data/ic-support/` owns the technical knowledge required to answer:

> How does Plasma support this IC?

It does **not** own commercial IC identity. Exact ICPN, manufacturer, family, package and current catalog admission remain owned by `data/device-catalog/`.

## Phase A boundary

This directory is a research/pilot contract. It does not change the Programming runtime, does not make a support claim, and cannot create PPU/Socket/real-IC validation evidence.

```text
Device Catalog (Who is this IC?)
        |
        | exact ICPN
        v
IC Support binding
        |
        +-- Programming Profile
        +-- Memory Geometry Profile
        +-- Package / Minimum Hardware Profile
        +-- Option Profile
        +-- Security Profile
        `-- Revision Overrides
```

The Phase A target is `STM32F103C8T6` + `STM32F103CBT6`. The pair is deliberately chosen to test profile reuse: they share the programming behavior under test while their Flash geometries differ.

## Layout

```text
data/ic-support/
├── schema/
├── evidence/
│   ├── sources.json
│   └── source_integrity.py
├── profiles/
│   ├── programming/
│   ├── memory-geometry/
│   ├── package-hardware/
│   ├── option/
│   ├── security/
│   └── revision/          # reserved for future artifacts; overrides live on bindings
├── bindings/
└── benchmarks/
    └── stm32f103c/
        ├── source-lock.json
        ├── extraction-contract.json
        ├── ground-truth.json
        └── generated/
```

Empty directories are not Git artifacts; `revision/` is a conceptual slot only until a real revision-specific record exists.

## Evidence rule

Every technical profile must cite evidence. Evidence has two distinct layers:

1. `evidence/sources.json` is the source catalog: document identity, revision, authority and retrieval location.
2. `benchmarks/stm32f103c/source-lock.json` is the immutable benchmark lock: exact source IDs plus content digests/byte lengths used to establish the answer key.

For the STM32F103C benchmark, ST `DS5319 Rev 20` and `PM0075 Rev 2` are SHA-256 pinned from bytes downloaded from official ST URLs. The retained Plasma STM32F1 commercial catalog is pinned by exact Git blob SHA.

The external PDFs are not redistributed in Git. Reproducibility is provided by the source lock plus `source_integrity.py verify`, which downloads the official URLs and fails if the bytes no longer match the lock.

No missing technical field may be filled by family-name inference. `pending_evidence` is valid; invented detail is not.

## Benchmark isolation

A real Harness/AI benchmark run must be isolated from the answer key. `benchmarks/stm32f103c/extraction-contract.json` defines the allowed source IDs and explicitly forbids reading:

- `ground-truth.json`;
- checked-in IC Support profiles;
- checked-in bindings.

The candidate must report the exact source digests it consumed. A result generated from a different source revision or after reading the answer key is not a valid benchmark sample.

## Validation

Run the deterministic/offline checks from the repository root:

```bash
python data/ic-support/validate.py
python data/ic-support/benchmarks/stm32f103c/validate_source_lock.py
python data/ic-support/compare_benchmark.py
python data/ic-support/test_ic_support.py
python data/ic-support/benchmarks/stm32f103c/test_extraction_contract.py
```

`validate.py` cross-checks each pilot ICPN against the existing STM32F1 commercial catalog, resolves every profile reference, validates evidence references, verifies geometry arithmetic, and enforces the intended C8/CB reuse boundary.

`validate_source_lock.py` proves that the answer key, extraction contract and locked evidence set agree and that the retained catalog Git blob has not drifted.

`compare_benchmark.py` compares the normalized observed projection with the source-locked ground truth. `validate_extraction_candidate.py` additionally enforces benchmark/source-lock metadata before accepting a Harness/AI candidate.

The networked source-byte verification is deliberately separate from deterministic CI:

```bash
python data/ic-support/evidence/source_integrity.py verify
```

The corresponding GitHub workflow is manual so an external ST outage cannot make ordinary Plasma CI non-deterministic.

## Explicit non-goals

- no runtime `ResolvedICSupport` implementation yet;
- no changes to `SiteManager`, Handler or OpenOCD execution;
- no PMode/EMode behavior change;
- no claim that Mock/CI means real IC support;
- no OTP/eFuse capability claim;
- no silicon-revision override without explicit errata/revision evidence;
- no migration of the existing Device Catalog;
- no claim that the current session is a valid blind AI extraction run.
