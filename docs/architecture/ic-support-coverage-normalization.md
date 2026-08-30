# IC Support Coverage Normalization

Status: **Phase 3.4 derived coverage model**

## 1. Purpose

Plasma must answer two different questions without conflating them:

```text
Device Catalog
  "Who is this IC?"
        |
        | exact ICPN
        v
IC Support
  "How does Plasma support this IC?"
```

The production Device Catalog can contain many exact commercial orderable part numbers that share the same underlying silicon behavior. A packaging/ordering suffix must not be counted as a new programming algorithm.

Phase 3.4 therefore adds a deterministic derived inventory:

```text
Exact ICPN
    |
    v
Base Device
    |
    v
Programming Profile
    |
    +--> OpenOCD backend mapping
    `--> Native PPU backend readiness
```

The inventory is derived at runtime from checked-in sources. It is **not another source of truth** and no generated copy of all catalog rows is checked in.

## 2. Ownership

The model preserves the existing ownership boundary:

- `data/device-catalog/` owns exact commercial identity, family, base device, package, Flash size and deterministic OpenOCD target mapping.
- `data/ic-support/profiles/` owns evidence-backed reusable technical behavior.
- `data/ic-support/bindings/` owns exact-ICPN-to-profile bindings.
- `data/ic-support/coverage_inventory.py` only joins these sources and reports coverage.

The core invariant remains:

```text
ICPN != Programming Algorithm
```

## 3. Current production baseline

The Phase 3.4 regression baseline after STM32F4 scale-out Batch 2 is:

```text
Exact ICPNs:                         124
Families:                              2
  STM32F1:                            75
  STM32F4:                            49
Base Devices:                         32
Deterministic OpenOCD-mapped ICPNs: 124
Direct IC Support-bound ICPNs:         2
Evidence-backed Programming Profiles:  1
Native PPU runtime-ready ICPNs:         0
```

These numbers describe different maturity layers and must not be collapsed into a single `supported=true` claim.

## 4. Example: commercial variants are not new algorithms

`STM32F407VGT6` and `STM32F407VGT6TR` are separate exact ICPNs because both are formal commercial orderable part numbers. In the production catalog they normalize to the same base device and technical catalog properties:

```text
STM32F407VGT6   --\
                  +--> STM32F407VG
STM32F407VGT6TR --/      |
                         +--> 1024 KiB Flash
                         +--> LQFP-100
                         `--> tcl/target/stm32f4x.cfg
```

They therefore count as:

```text
2 Exact ICPNs
1 Base Device
0 evidence-backed Plasma Programming Profiles today
```

The last value is intentionally zero for this base device. The common OpenOCD target is deterministic catalog evidence, but it is not enough to claim that Plasma has already extracted and admitted the full programming algorithm needed by the Native PPU Driver.

## 5. Programming Profile meaning

A Programming Profile is the reusable algorithmic Flash behavior already defined by the IC Support architecture. It owns facts such as:

- Flash controller registers;
- unlock keys and sequence;
- program sequence and granularity;
- erase capabilities;
- busy/error handling inputs;
- programming prerequisites.

It does not own commercial packaging suffixes. Memory geometry, package/minimum hardware, option/configuration behavior and security remain separate profile kinds.

Consequently, equal OpenOCD target configuration is useful routing evidence but is **not sufficient proof of complete Programming Profile equivalence**.

## 6. Backend interpretation

For every production exact ICPN, the derived inventory reports two independent backend states.

### OpenOCD

`deterministic_target_mapped` means the admitted Device Catalog has a deterministic target configuration such as:

```text
tcl/target/stm32f1x.cfg
tcl/target/stm32f4x.cfg
```

This is a routing/mapping statement, not a PPU/Socket or real-IC validation statement.

### Native PPU

The current Native PPU runtime does not yet consume `ResolvedICSupport`; therefore all exact ICPNs remain `runtime_ready=false` in this Phase 3.4 inventory, even when a research/pilot Programming Profile exists.

For the current STM32F103C pilot, two exact ICPNs are directly bound to the evidence-backed pilot profile:

```text
STM32F103C8T6  --\
                  +--> stm32f1-medium-density-flash-v0
STM32F103CBT6  --/
```

That profile is reusable programming knowledge, but the architecture explicitly remains research/pilot-only until a future approved runtime resolver/driver phase connects it to execution.

## 7. Fail-closed normalization rules

`coverage_inventory.py` rejects the derived view when any of these invariants fail:

1. production catalog source SHA-256 or Git blob binding drifts;
2. a production exact ICPN is duplicated;
3. an IC Support binding refers to an ICPN outside the production catalog;
4. a Programming Profile reference is dangling or has the wrong kind;
5. one base device spans conflicting families;
6. one base device contains conflicting Flash sizes;
7. one base device maps to conflicting OpenOCD targets;
8. directly bound exact ICPNs of one base device disagree on Programming Profile identity.

These checks prevent commercial suffix expansion from silently creating contradictory technical identities.

## 8. Commands

From repository root:

```bash
python data/ic-support/coverage_inventory.py
python data/ic-support/coverage_inventory.py --summary
python data/ic-support/coverage_inventory.py --json
python data/ic-support/test_coverage_inventory.py
```

The complete JSON output is a deterministic derived view suitable for tooling, review and future API/resolver work. It is intentionally generated on demand instead of checked in as a second catalog.

## 9. Coverage KPIs going forward

Every future catalog/profile expansion should report at least:

```text
Exact ICPNs
Base Devices
Evidence-backed Programming Profiles
Direct IC Support-bound exact ICPNs
Deterministic OpenOCD-mapped exact ICPNs
Native PPU runtime-ready exact ICPNs
PPU-verified support
Socket-verified support
```

A future scale-out PR can therefore state, for example:

```text
+15 Exact ICPNs
+5 Base Devices
+0 Programming Profiles
```

or:

```text
+12 Exact ICPNs
+3 Base Devices
+1 Programming Profile
```

The second case represents a real increase in programming-technology coverage; the first may primarily increase commercial ordering coverage.

## 10. Explicit non-goals

Phase 3.4 does not:

- add new Device Catalog ICPNs;
- infer missing Programming Profiles from family names or OpenOCD cfg names;
- promote the STM32F103C pilot to production runtime support;
- implement `ResolvedICSupport`;
- change Handler/OpenOCD execution;
- implement a Native PPU Driver algorithm;
- claim PPU, Socket or real-IC validation;
- deploy or restart Plasma services;
- perform Z2/FPGA/real-target operations.
