# IC Support Reusable Profile Architecture

Status: **Plan / Phase A pilot implemented as research data only**

## 1. Decision

Plasma separates two ownership domains:

```text
Device Catalog
  "Who is this IC?"
        |
        | exact ICPN
        v
IC Support
  "How does Plasma support this IC?"
```

`data/device-catalog/` remains the commercial identity source of truth. `data/ic-support/` adds reusable technical profiles and exact-ICPN bindings. IC Support must not duplicate the commercial catalog.

The core invariant is:

```text
ICPN != Programming Algorithm
```

An exact commercial part number binds to reusable technical behavior; it does not own a copied full programming specification.

## 2. Why this is needed now

Repository inspection at the start of Phase A found a deliberate gap between catalog resolution and programming execution:

- `plasma_web/device_catalog.py` resolves part-number-first catalog records.
- the Gateway resolves an Engineering `target_device` against that catalog.
- `SiteManager` still constructs `STM32F103Handler` for every enabled Site.
- `STM32F103Handler` still names `STM32F103C8T6` directly.
- `OpenOCDInterface.erase()` still contains one fixed Flash erase address/range, while Program/Verify/Read remain hardware-specific placeholders.

Therefore the correct next boundary is not to patch more part numbers into the Handler. It is to establish a deterministic IC Support knowledge model first, prove it on a known target, then introduce a resolver in a later approved phase.

## 3. Relationship to existing contracts

[Device Support and Validation](device-support-validation.md) remains the current contract for support status, programming-configuration identity, PPU/Socket evidence, engineering validation, field-use evidence, lifecycle, and audit boundaries.

This document adds a narrower missing concept: **technical profile decomposition and reuse**.

It does not redefine:

- PPU/Site/Socket validation;
- engineering evidence;
- pilot/production reports;
- Batch/Job execution evidence;
- Device Catalog identity admission.

## 4. Phase A data model

An exact ICPN resolves as:

```text
Device Catalog exact ICPN
        |
        v
IC Support binding
        |
        +-- Programming Profile
        +-- Memory Geometry Profile
        +-- Package / Minimum Hardware Profile
        +-- Option / Configuration Profile
        +-- Security Profile
        `-- Revision Overrides[]
```

### 4.1 Programming Profile

Owns only algorithmic Flash behavior: controller registers, unlock sequence, program/erase flow, busy/error handling inputs, granularity constraints, and prerequisites.

It must not own package pins or commercial suffixes.

### 4.2 Memory Geometry Profile

Owns address ranges, sizes, page/sector geometry, bank topology and erase/program granularity that vary independently from the programming algorithm.

### 4.3 Package / Minimum Hardware Profile

Owns package-dependent physical requirements and programming interfaces. Phase A intentionally stops before pin-level minimum hardware because the pilot has not yet retained/pinned the required pin/electrical evidence. That field is fail-closed as `pending_evidence`.

### 4.4 Option Profile

Owns option/configuration storage, encoding, unlock/program/reload semantics and reserved-bit preservation rules.

### 4.5 Security Profile

Owns read/write protection and destructive security transitions. Security behavior is not inferred from the main-Flash profile.

### 4.6 Revision Overrides

Revision changes are sparse overrides on an exact binding, not another duplicated complete profile. The Phase A pilot has an empty override list because no silicon-revision/errata comparison has yet been admitted into the pilot evidence.

## 5. STM32F103C pilot

The first target is deliberately small:

```text
STM32F103C8T6  -> STM32F103C8 -> 64 KiB
STM32F103CBT6  -> STM32F103CB -> 128 KiB
```

Both exact ICPNs already exist in the retained STM32F1 Device Catalog. The manufacturer programming manual defines STM32F103x8/xB as medium-density Flash devices and provides the common Flash programming model. The datasheet distinguishes the 64/128 KiB variants.

Expected decomposition:

| Profile kind | C8T6 vs CBT6 |
|---|---|
| Programming | shared |
| Memory Geometry | different |
| Package / Hardware | shared at current LQFP48/debug-interface evidence depth |
| Option | shared |
| Security | shared |
| Revision Override | none admitted yet |

This tests two independent properties:

1. **Extraction accuracy** — are addresses, sizes, keys, sequences and security effects correct?
2. **Normalization accuracy** — are equal behaviors actually shared, and genuinely different geometry kept separate?

A result can therefore be factually correct yet architecturally wrong if it duplicates an identical Programming Profile per ICPN.

## 6. Ground-truth evidence

Phase A uses:

- ST `DS5319 Rev 20` for STM32F103x8/xB device scope, 64/128 KiB Flash, package family and debug-interface facts.
- ST `PM0075 Rev 2` for medium-density Flash organization, register map, unlock/program/erase behavior, Option Bytes and protection behavior.
- Plasma's retained STM32F1 commercial ICPN catalog for exact commercial identity binding.

The ST source records currently identify document number/revision/URL but the remote PDF bytes are not yet content-addressed in this repository. Therefore the checked-in benchmark is explicitly a **pilot ground truth**, not the final immutable benchmark baseline.

Before scale-out, the evidence pipeline must retain or otherwise SHA-256 pin the exact manufacturer document bytes used to establish ground truth.

## 7. Deterministic validation

`data/ic-support/validate.py` must fail closed on:

- duplicate or dangling profile IDs;
- unknown evidence source IDs;
- exact ICPN missing from Device Catalog;
- manufacturer/base-device/package/pin-count/Flash-size/OpenOCD mapping drift;
- profile-kind/reference mismatch;
- invalid geometry arithmetic;
- C8/CB incorrectly sharing Memory Geometry;
- C8/CB unnecessarily splitting Programming/Package/Option/Security profiles;
- invented revision overrides;
- promotion of incomplete pin-level minimum hardware into runtime-ready status.

`compare_benchmark.py` creates a stable projection independent of file layout and compares it against the checked-in STM32F103C ground truth. A future Harness/AI run must emit the same projection; it must not modify the answer key.

## 8. Runtime boundary

Phase A intentionally stops before:

```text
ICPN
  -> IC Support Resolver
  -> ResolvedICSupport
  -> Programming Handler
```

A future runtime phase may introduce `ResolvedICSupport` as the only programming-facing aggregate. The Handler should then consume resolved technical behavior instead of commercial part-number branches.

That phase must separately address the current fixed `STM32F103Handler` ownership and fixed OpenOCD erase template. Phase A does not change either.

## 9. Scale-out gates

The architecture may expand beyond STM32F103C only after all of the following are true:

1. official source documents are content-pinned;
2. the pilot validator and benchmark remain deterministic/offline;
3. a Harness/AI extraction run can be compared without sharing its generated answer with ground truth creation;
4. unresolved fields remain explicit instead of inferred;
5. profile reuse rules have both positive and negative test cases.

Suggested next challenge after C8/CB is to add STM32F103R/V or another density class specifically to force a boundary change rather than merely add volume.

## 10. Non-goals of Phase A

- no production `ResolvedICSupport` code;
- no IC Selector behavior change;
- no PMode/EMode behavior change;
- no Handler/OpenOCD execution change;
- no Z2/PPU/Socket/real-IC test claim;
- no bulk migration of the 7,000+ catalog identifiers;
- no OTP/eFuse support claim;
- no security operation approval gate implementation yet.
