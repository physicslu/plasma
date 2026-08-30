# IC Support Reusable Profile Architecture

Status: **Plan / Phase A source-locked pilot implemented as research data only**

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

## 6. Ground-truth evidence and source lock

Phase A uses:

- ST `DS5319 Rev 20` for STM32F103x8/xB device scope, 64/128 KiB Flash, package family and debug-interface facts.
- ST `PM0075 Rev 2` for medium-density Flash organization, register map, unlock/program/erase behavior, Option Bytes and protection behavior.
- Plasma's retained STM32F1 commercial ICPN catalog for exact commercial identity binding.

Evidence identity and benchmark integrity are deliberately separated:

```text
sources.json
  -> source identity / revision / authority / retrieval location

source-lock.json
  -> exact bytes or exact Git blob used by this benchmark
```

For `stm32f103c-source-lock-v0`:

- DS5319 Rev 20 is pinned by SHA-256 and byte length from the official ST PDF bytes.
- PM0075 Rev 2 is pinned by SHA-256 and byte length from the official ST PDF bytes.
- the retained STM32F1 commercial catalog is pinned by exact Git blob SHA.

The manufacturer PDFs are not redistributed in Git. `source_integrity.py verify` can re-download the official URLs and fail if the current bytes differ from the checked-in source lock. This networked check is intentionally separate from ordinary deterministic CI.

The checked-in `ground-truth.json` is now explicitly bound to `stm32f103c-source-lock-v0`; changing source bytes therefore requires a new reviewed lock/ground-truth relationship rather than silently mutating the benchmark.

## 7. Deterministic validation and extraction isolation

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

`benchmarks/stm32f103c/validate_source_lock.py` additionally checks that source lock, Ground Truth, extraction contract and retained catalog blob all agree.

`compare_benchmark.py` creates a stable projection independent of file layout and compares it against the checked-in STM32F103C ground truth.

A real Harness/AI benchmark run has a stricter rule: it must follow `extraction-contract.json` and must not be given the answer key. Specifically, the extraction process may consume only the locked source set and target ICPNs; it must not read:

- `ground-truth.json`;
- checked-in IC Support profiles;
- checked-in IC Support bindings.

The candidate must report the exact source digests it consumed. `validate_extraction_candidate.py` rejects a candidate produced from a different source lock even if its observed values happen to match.

This session is not treated as a valid blind extraction run because the existing Ground Truth and profiles were already visible while the benchmark contract was being developed.

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

Before expanding the architecture beyond the current STM32F103C pilot, the following conditions apply:

1. **Source lock — satisfied for the current C8/CB benchmark.** The exact DS5319 Rev 20, PM0075 Rev 2 and retained catalog inputs are content/blob pinned.
2. **Deterministic validation — satisfied for the current pilot contract.** Ordinary benchmark validation remains offline and deterministic.
3. **Independent extraction — not yet satisfied.** A fresh Harness/AI run must execute without Ground Truth/profile/binding leakage and produce a candidate carrying the exact source lock.
4. **Unresolved fields remain explicit.** Missing minimum pin-level hardware evidence remains fail-closed rather than inferred.
5. **Profile reuse has positive and negative tests.** Shared behavior and intentionally different memory geometry are both regression tested.

The next scientific step is therefore **not** bulk STM32F1 expansion. It is one isolated extraction run against the locked STM32F103C benchmark. Only after that result is understood should the target expand to STM32F103R/V or another density class that forces a meaningful profile-boundary decision.

## 10. Non-goals of Phase A

- no production `ResolvedICSupport` code;
- no IC Selector behavior change;
- no PMode/EMode behavior change;
- no Handler/OpenOCD execution change;
- no Z2/PPU/Socket/real-IC test claim;
- no bulk migration of the 7,000+ catalog identifiers;
- no OTP/eFuse support claim;
- no security operation approval gate implementation yet;
- no claim that contract self-tests are equivalent to a blind Harness/AI extraction benchmark.
