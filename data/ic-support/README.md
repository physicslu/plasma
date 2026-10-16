# Plasma AI IC Support — Research Pilot

`data/ic-support/` owns the AI-assisted research pipeline for deriving evidence-backed candidate programming knowledge and reusable programming methods from manufacturer documentation.

It does **not** own commercial IC identity. Exact ICPN, manufacturer, family, package and current catalog admission remain owned by `data/device-catalog/`.

It also does **not** own Plasma software runtime support. OpenOCD runtime integration, PPU implementation, Socket support, electrical qualification and physical programming qualification are separate capability domains.

## Phase A boundary

This directory is a research/pilot contract. It does not change the Programming runtime, does not make a software-support claim, and cannot create PPU/Socket/real-IC validation evidence.

```text
Manufacturer evidence
        |
        v
AI IC Support research
        |
        +-- Programming Profile candidate
        +-- Memory Geometry Profile candidate
        +-- Package / Minimum Hardware candidate
        +-- Option Profile candidate
        +-- Security Profile candidate
        `-- Revision / applicability evidence

Device Catalog -------------------------------> User-selectable ICPN
        |                                             |
        | identity / metadata                         v
        |                                      Capability status
        |                                      OpenOCD / PPU /
        |                                      Socket / HIL
        |
        `---- may be referenced by research, but catalog admission
              does not imply research or runtime support
```

Research output is not automatically promoted into production software. A future runtime capability/driver promotion must have its own explicit contract, implementation and validation boundary.

The Phase A target is `STM32F103C8T6` + `STM32F103CBT6`. The pair is deliberately chosen to test profile reuse: they share the programming behavior under test while their Flash geometries differ.

## Layout

```text
data/ic-support/
├── schema/
├── evidence/
│   ├── sources.json
│   └── source_integrity.py
├── evidence-pack/
│   ├── schema/
│   ├── fixtures/
│   ├── policies/
│   ├── contract.py
│   ├── preprocessing.py
│   ├── semantic_pack.py
│   ├── normalization-v0.json
│   ├── taxonomy-v0.json
│   └── rules-v0.json
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
        ├── evidence-pack-benchmark-v0.json
        ├── ground-truth.json
        └── generated/
```

Empty directories are not Git artifacts; `revision/` is a conceptual slot only until a real revision-specific record exists.

## Evidence rule

Every technical profile must cite evidence. Evidence now has five separate responsibilities:

1. `evidence/sources.json` is the logical source catalog: document identity, revision, authority and retrieval location.
2. `benchmarks/stm32f103c/source-lock.json` is the immutable benchmark lock: exact source IDs plus content digests/byte lengths used to establish the answer key.
3. `evidence-pack/preprocessing.py` deterministically converts one exact source-locked PDF into a structural manifest with physical-page preservation, preprocessing/normalization fingerprints, structural candidates and explicit-reference candidates. It does not perform semantic evidence classification.
4. `evidence-pack/semantic_pack.py` resolves an admitted deterministic semantic policy against that manifest, builds page-atomic Evidence Units, applies mandatory seeds and dependency closure, and creates an Evidence Pack plus applicability/bundle artifacts.
5. `evidence-pack/contract.py` defines reusable Evidence Unit Catalog, Evidence Pack, evidence-backed Applicability Binding and per-target Evidence Bundle contracts and trust boundaries.

Evidence Packs do not replace source locks and do not grant IC Support or production admission. A document may be shared by many ICPNs; the pack is document/purpose scoped and reusable rather than duplicated per part number. Exact ICPNs resolve packs through evidence-backed applicability claims.

For the STM32F103C benchmark, ST `DS5319 Rev 20` and `PM0075 Rev 2` are SHA-256 pinned from bytes downloaded from official ST URLs. The retained Plasma STM32F1 commercial catalog is pinned by exact Git blob SHA.

The external PDFs are not redistributed in Git. Reproducibility is provided by the source lock plus `source_integrity.py verify`, which downloads the official URLs and fails if the bytes no longer match the lock. Evidence processing retains policy, structural metadata, recipes and digests rather than manufacturer body text.

Document preprocessing fingerprints the exact `pdftotext` version and arguments, the versioned normalization contract and the preprocessing implementation bytes. Every physical PDF page must survive as exactly one `PAGE` unit even if structural heading detection fails. Section/table/figure detection remains candidate metadata.

The DS5319 semantic policy uses exact section labels plus heading regexes and must resolve each admitted rule uniquely. Table-of-contents aliases or ambiguous structural targets cannot silently satisfy a rule. Physical pages are the v0 atomic semantic Evidence Units; dependency closure may pull an otherwise excluded page back into the pack when a deterministic explicit reference uniquely resolves.

No missing technical field may be filled by family-name inference. `pending_evidence` is valid; invented detail is not. Evidence Pack applicability follows the same rule: manufacturer scope expressions require included evidence and an unbound exact ICPN fails closed.

## Benchmark isolation

A real Harness/AI benchmark run must be isolated from the answer key. `benchmarks/stm32f103c/extraction-contract.json` defines the allowed source IDs and explicitly forbids reading:

- `ground-truth.json`;
- checked-in IC Support profiles;
- checked-in bindings.

The candidate must report the exact source digests it consumed. A result generated from a different source revision or after reading the answer key is not a valid benchmark sample.

The manufacturer-only Evidence Pack A/B experiment is deliberately separate from the formal blind benchmark. `evidence-pack-benchmark-v0.json` is now a runnable contract comparing full DS5319 + full PM0075 against deterministic DS5319 Evidence Pack + full PM0075 while keeping the existing formal three-source lock unchanged.

Actual manufacturer-content-derived pack outputs are generated outside Git. `.github/workflows/ic-evidence-live-validation.yml` separately verifies the exact DS5319 source and semantic policy against the real PDF while retaining only metadata/digests as an artifact; ordinary deterministic AI IC Support research CI remains independent of ST availability.

## STM32F103C8T6 Socket design-input pilot

The manufacturer-near `package_hardware` profile remains the shared LQFP48/debug-interface fact used by the source-locked C8/CB research benchmark. Socket engineering is composed separately through the independent `socket-design/` sidecar registry; frozen IC Support bindings and OpenOCD qualification inputs remain byte-identical.

`socket-design/profiles/stm32f103c8t6-lqfp48-programming-hardware-v1.json` is the first design-ready overlay, bound through `socket-design/bindings/stm32f103c8t6-v1.json`. It records the source-backed LQFP48 mechanics, all mandatory VDD/VSS/VDDA/VSSA/VBAT contacts, SWDIO/SWCLK/NRST physical pins, deterministic BOOT0 main-Flash startup policy, decoupling/reset requirements and explicit unresolved HIL items. It can be exported with:

```bash
PYTHONPATH=software/python python -m plasma_core.ic_support \
  --icpn STM32F103C8T6 --socket-design-input
```

The output is **design input only**. It never grants Socket compatibility, Site electrical compatibility, runtime hardware readiness, physical programming qualification or Catalog Level 3. A real Socket model/revision, schematic/netlist continuity checks and PPU/Site/DUT HIL remain separate gates.

## Manufacturer-only native-programmer pilot

The STM32F103C8T6 pilot now has a separate manufacturer-only knowledge baseline under
`manufacturer-baseline/`. Its exact bytes are SHA-256 locked before any OpenOCD source
is inspected. The baseline includes Device Profile facts, operating electrical
characteristics, memory map, Programming Interface facts, programming electrical
conditions and machine-readable Flash unlock/erase/program semantics.

The subsequent OpenOCD comparison lives under `openocd-comparison/` and is analysis
only. Backend defaults and optimizations cannot mutate the manufacturer baseline. This is
the reference method for future Plasma-native programmer knowledge extraction.

## Manufacturer Enrichment Coverage

Manufacturer Enrichment Coverage is measured independently from Device Catalog identity and runtime/hardware qualification.

The v1 framework is documented in:

```text
docs/architecture/manufacturer-enrichment-coverage-v1.md
```

Coverage levels are monotonic:

```text
M0 Production exact identity
M1 Manufacturer Device Basic Profile
M2 Manufacturer Programming Profile
M3 Manufacturer-derived executable semantics
M4 Independent software differential
M5 Physical HIL qualification
```

Reusable manufacturer facts must use explicit exact-ICPN applicability through
`manufacturer_enrichment_scope.py`. Family-name similarity, OpenOCD mapping, or a shared
Flash-controller label never grants applicability by itself.

Current deterministic reporting:

```bash
python data/ic-support/coverage_inventory.py --manufacturer-summary
python data/ic-support/coverage_inventory.py --icpn STM32F103C8T6
python data/ic-support/coverage_inventory.py --icpn STM32F103R8T6
python data/ic-support/test_manufacturer_enrichment_scope.py
```

The coverage registry is research-only and cannot grant runtime or hardware authority.


Manufacturer Device Basic Profile v1 is stored as one explicit family profile per admitted
family under `device-basic/*-device-basic-v1.json`. The current registry covers all
**1,622** Production exact ICPNs across STM32F1 (280), STM32F2 (105), STM32C0 (226), STM32G0 (406), STM32G4 (273), STM32U0 (68), STM32U3 (107), STM32L5 (49), STM32H7RS (36), STM32WBA5X (40), and STM32N6 (32).
Every profile uses the fixed IC Information contract:
ICPN / Base Device / Package / Pin Count / Flash / RAM / Operating VDD /
I/O Supply / VDDA / Operating Temperature. I/O Supply and VDDA remain null unless
directly established by the allowed Product Selector/eStore evidence; they are never copied
from VDD. STM32F2 admits RAM and Operating VDD from direct ST Product Selector observations while I/O Supply and VDDA remain null. STM32G4 is the first family profile with directly admitted VDDA evidence from
ST eStore, while I/O Supply remains null. Basic Profile admission does not grant Programming Profile authority.

The Basic Profile deliberately uses a lighter official-product-metadata provenance class
than the programming baseline: ST Product Selector / eStore observations are retained
with official URLs and observation date, but no SHA-256 content lock is fabricated for
dynamic web content. Programming semantics continue to require the stronger manufacturer
evidence chain.

The remaining-ST completion ledger is:

```text
data/ic-support/device-basic/st-m1-remaining-enrichment-v1.json
```

It records the completed review of the 3,339 ST exact ICPNs that were outside the 1,290
baseline: 332 are admitted by six new complete family profiles and 3,007 are explicitly
`blocked_evidence_gap`. A blocked disposition means the family was reviewed but cannot
be promoted without violating the Product Selector/eStore-only derivation rule, losing
manufacturer semantics, or inventing source precedence. It is not an unreviewed backlog.

## Validation

Run the deterministic/offline checks from the repository root:

```bash
python data/ic-support/validate.py
python data/ic-support/socket-design/validate.py
python data/ic-support/evidence-pack/validate_contract.py
python data/ic-support/evidence-pack/validate_preprocessing.py
python data/ic-support/evidence-pack/validate_semantic_pack.py
python data/ic-support/benchmarks/stm32f103c/validate_source_lock.py
python data/ic-support/compare_benchmark.py
python data/ic-support/test_ic_support.py
python data/ic-support/benchmarks/stm32f103c/test_extraction_contract.py
```

`validate.py` cross-checks each pilot ICPN against the existing STM32F1 commercial catalog, resolves every profile reference, validates evidence references, verifies geometry arithmetic, and enforces the intended C8/CB reuse boundary.

`evidence-pack/validate_contract.py` validates the Evidence Pack foundation: exact source-lock fingerprint binding, reproducibility identities, mandatory/unknown fail-closed behavior, dependency closure, AI add-only enrichment, many-to-many pack reuse, applicability evidence and denial of canonical/production admission.

`evidence-pack/validate_preprocessing.py` validates deterministic preprocessing invariants using synthetic content only: newline/whitespace normalization, physical-page preservation, structural-candidate isolation, ambiguous-reference refusal, source-lock drift rejection, manifest mutation detection and identity sensitivity to tool/normalization/builder changes.

`evidence-pack/validate_semantic_pack.py` validates the DS5319 deterministic semantic policy, page reduction, TOC-decoy rejection, C8/CB pack reuse, policy/source-lock drift rejection, explicit dependency closure and reduced-context materialization using metadata/synthetic content only.

`validate_source_lock.py` proves that the answer key, extraction contract and locked evidence set agree and that the retained catalog Git blob has not drifted.

`compare_benchmark.py` compares the normalized observed projection with the source-locked ground truth. `validate_extraction_candidate.py` additionally enforces benchmark/source-lock metadata before accepting a Harness/AI candidate.

The general networked source-byte verification remains separate from deterministic CI:

```bash
python data/ic-support/evidence/source_integrity.py verify
```

## Explicit non-goals

- no AI/LLM semantic classifier or generic RAG implementation in the deterministic Evidence Pack path;
- no AI authority to exclude evidence or create authoritative dependency edges;
- no automatic promotion of research output into Plasma software runtime support;
- no runtime `ResolvedICSupport` change from this workstream;
- no changes to `SiteManager`, Handler or OpenOCD execution;
- no PMode/EMode behavior change;
- no claim that Mock/CI means real IC support;
- no OTP/eFuse capability claim;
- no silicon-revision override without explicit errata/revision evidence;
- no migration of the existing Device Catalog;
- no claim that the current session is a valid blind AI extraction run.
