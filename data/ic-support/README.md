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
```

Empty directories are not Git artifacts; `revision/` is a conceptual slot only until a real revision-specific record exists.

## Evidence rule

Every technical profile must cite evidence. The two ST documents used by this pilot are identified by document number and revision. Their remote PDF bytes are **not yet SHA-256 pinned**, so this is a pilot ground truth, not an immutable long-term benchmark artifact. Scale-out must first retain or otherwise content-pin the exact manufacturer documents.

No missing technical field may be filled by family-name inference. `pending_evidence` is valid; invented detail is not.

## Validation

Run from the repository root:

```bash
python data/ic-support/validate.py
python data/ic-support/compare_benchmark.py
python data/ic-support/test_ic_support.py
```

`validate.py` cross-checks each pilot ICPN against the existing STM32F1 commercial catalog, resolves every profile reference, validates evidence references, verifies geometry arithmetic, and enforces the intended C8/CB reuse boundary.

`compare_benchmark.py` builds a deterministic projection from the checked-in profiles/bindings and compares it with the STM32F103C pilot ground truth. A future Harness/AI extractor can emit the same `observed` projection and pass it using `--candidate FILE`.

## Explicit non-goals

- no runtime `ResolvedICSupport` implementation yet;
- no changes to `SiteManager`, Handler or OpenOCD execution;
- no PMode/EMode behavior change;
- no claim that Mock/CI means real IC support;
- no OTP/eFuse capability claim;
- no silicon-revision override without explicit errata/revision evidence;
- no migration of the existing Device Catalog.
