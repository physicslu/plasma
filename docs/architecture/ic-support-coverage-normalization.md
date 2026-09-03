# IC Support Coverage Normalization

Status: **Current derived coverage contract; introduced in Phase 3.4 and extended by the runtime resolver / OpenOCD planning phases**

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

Plasma therefore maintains a deterministic derived inventory:

```text
Exact ICPN
    |
    v
Base Device
    |
    v
Programming Profile
    |
    +--> OpenOCD backend mapping / plan readiness
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

The executable coverage inventory on the current production Device Catalog is:

```text
Exact ICPNs:                           286
Families:                                2
  STM32F1:                              75
  STM32F4:                             211
Base Devices:                           91
Deterministic OpenOCD-mapped ICPNs:    286
Direct IC Support-bound ICPNs:           2
Unresolved Programming Profile ICPNs:  284
Evidence-backed Programming Profiles:    1
Native PPU runtime-ready ICPNs:           0
```

These values are enforced by `data/ic-support/test_coverage_inventory.py` and are derived from the production Device Catalog manifest plus its admitted STM32F1/STM32F4 commercial ICPN sources.

The counts describe different maturity layers and must not be collapsed into a single `supported=true` claim. In particular, `286 deterministic OpenOCD-mapped ICPNs` does **not** mean Plasma has 286 evidence-backed Programming Profiles or 286 hardware-validated programming targets.

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

The last value is intentionally zero for this base device. The common OpenOCD target is deterministic catalog evidence, but it is not enough to claim that Plasma has extracted and admitted the complete Programming Profile needed for production execution.

## 5. Programming Profile meaning

A Programming Profile is reusable algorithmic Flash behavior. It owns facts such as:

- Flash controller registers;
- unlock keys and sequence;
- program sequence and granularity;
- erase capabilities;
- busy/error handling inputs;
- programming prerequisites.

It does not own commercial packaging suffixes. Memory geometry, package/minimum hardware, option/configuration behavior and security remain separate profile kinds.

Consequently, equal OpenOCD target configuration is useful routing evidence but is **not sufficient proof of complete Programming Profile equivalence**.

## 6. Backend interpretation

For every production exact ICPN, the derived inventory reports independent backend states.

### OpenOCD mapping

`deterministic_target_mapped` means the admitted Device Catalog has a deterministic target configuration such as:

```text
tcl/target/stm32f1x.cfg
tcl/target/stm32f4x.cfg
```

This is a routing/mapping statement, not a PPU/Socket or real-IC validation statement.

For the currently bound STM32F103C pilot targets, the runtime resolver can resolve reusable IC Support profiles and the OpenOCD plan compiler can generate deterministic plans. The software-only compiled-plan executor is also validated for the bound profile. Production hardware execution remains fail-closed.

### Native PPU

The runtime resolver exists, but the Plasma Native / FPGA programming backend is not runtime-ready. Therefore all production exact ICPNs remain `native_ppu.runtime_ready=false` in the coverage inventory.

The two current exact ICPN bindings are:

```text
STM32F103C8T6  --\
                  +--> stm32f1-medium-density-flash-v0
STM32F103CBT6  --/
```

They share one evidence-backed Programming Profile while using distinct Memory Geometry Profiles. This is reusable programming knowledge, not a claim that a Native PPU Driver or physical socket path is production-ready.

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

## 8. Cross-domain CI dependency

IC Support coverage depends on production Device Catalog inputs, not only on `data/ic-support/**`.

`IC Support validation` must therefore run when any of the directly consumed production inputs change:

```text
data/device-catalog/production/icpn-v1-manifest.json
data/device-catalog/research/stm32f1-commercial-icpn.csv
data/device-catalog/research/stm32f4-commercial-icpn.csv
```

This dependency is intentional. A Device Catalog admission that changes production coverage must re-run IC Support coverage normalization in the same PR so the derived inventory cannot silently drift behind the catalog.

## 9. Commands

From repository root:

```bash
python data/ic-support/coverage_inventory.py
python data/ic-support/coverage_inventory.py --summary
python data/ic-support/coverage_inventory.py --json
python data/ic-support/test_coverage_inventory.py
```

The complete JSON output is a deterministic derived view suitable for tooling, review and future API/resolver work. It is intentionally generated on demand instead of checked in as a second catalog.

## 10. Coverage KPIs going forward

Every future catalog/profile expansion should report at least:

```text
Exact ICPNs
Base Devices
Evidence-backed Programming Profiles
Direct IC Support-bound exact ICPNs
Unresolved Programming Profile exact ICPNs
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

## 11. Explicit non-goals

This coverage model does not:

- infer missing Programming Profiles from family names or OpenOCD cfg names;
- promote deterministic OpenOCD target mapping to programming-support proof;
- promote the STM32F103C profile to hardware runtime readiness;
- implement a Native PPU Driver algorithm;
- claim PPU, Socket or real-IC validation;
- deploy or restart Plasma services;
- perform Z2/FPGA/real-target operations.

Historical Phase 3.x / Phase 4.x admission documents retain the production counts that were true at those historical checkpoints. This Current document reports the executable production coverage enforced by the present repository state.
