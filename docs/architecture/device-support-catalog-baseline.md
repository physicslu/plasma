# Device Support Catalog Baseline Statistics

Status: research baseline for the device-support implementation plan

## 1. Source snapshot

| Field | Value |
|---|---|
| Canonical upstream | OpenOCD SourceForge `master` |
| Verified mirror | `openocd-org/openocd` |
| Commit | `56b8d93fbe61a78dc903d770820d6d896b6d8134` |
| Commit date | 2026-08-18 |
| Scope | Recursive `tcl/target/**/*.cfg` |

All counts in this document belong to this exact snapshot. A later OpenOCD, CMSIS Pack, vendor DFP, or ESP-IDF refresh must create a new baseline rather than silently replacing these numbers.

## 2. OpenOCD target CFG count

| Metric | Count |
|---|---:|
| Recursive target CFG files | 399 |
| Auto-classified target records | 325 |
| Target records needing catalog review | 51 |
| Internal/helper records | 23 |
| CFG files with one or more statically resolved CPU architectures | 381 |
| CFG files without a created/resolved CPU target | 18 |
| Heterogeneous/multi-architecture CFG files | 27 |
| Distinct normalized CPU architecture groups | 18 |
| CPU-architecture memberships | 411 |

Architecture memberships total more than 399 because one heterogeneous SoC CFG may create more than one CPU architecture, for example Cortex-A plus Cortex-M or AArch64 plus Cortex-M.

## 3. CPU architecture membership by CFG

| Normalized CPU architecture | CFG memberships |
|---|---:|
| ARM Cortex-M | 178 |
| ARM classic (ARM7/9/11, FA526, Feroceon, XScale) | 76 |
| ARM Cortex-A (AArch32) | 35 |
| Arm AArch64 | 35 |
| RISC-V | 27 |
| MIPS | 20 |
| STM8 | 11 |
| ARM Cortex-R / Armv8-R | 10 |
| Xtensa | 4 |
| AVR | 3 |
| ARC | 3 |
| DSP56800 | 2 |
| x86 Quark | 2 |
| AVR32 | 1 |
| Dragonite | 1 |
| DSP56300 | 1 |
| Esi-RISC | 1 |
| OpenRISC | 1 |
| **Total memberships** | **411** |

The normalized architecture is derived from the CPU target type created by the Tcl configuration, directly or through a statically resolvable `source [find target/...cfg]` include. Non-CPU access targets such as `mem_ap` are not counted as CPU architectures.

## 4. CFG files without a resolved CPU target

These 18 files do not create or statically resolve a CPU target. Most are helpers, core-description fragments, transport/reset utilities, or negative-test inputs; their presence must not be interpreted as 18 additional supported CPU architectures.

```text
tcl/target/at32ap7000.cfg
tcl/target/esp_common.cfg
tcl/target/hpmicro/hpm_common.cfg
tcl/target/hpmicro/hpm_common_csr.cfg
tcl/target/hpmicro/hpm_common_csr_lite.cfg
tcl/target/hpmicro/hpm_reset.cfg
tcl/target/imx.cfg
tcl/target/nordic/common.cfg
tcl/target/renesas_rcar_reset_common.cfg
tcl/target/test_syntax_error.cfg
tcl/target/ti/cjtag.cfg
tcl/target/ti/davinci.cfg
tcl/target/ti/icepick.cfg
tcl/target/xtensa-core-esp32.cfg
tcl/target/xtensa-core-esp32s2.cfg
tcl/target/xtensa-core-esp32s3.cfg
tcl/target/xtensa-core-nxp_rt600.cfg
tcl/target/xtensa-core-xt8.cfg
```

For example, `at32ap7000.cfg` documents an AVR32 AP7 device but explicitly notes that an AVR32 target still needs OpenOCD infrastructure. It therefore remains outside the resolved CPU-target count.

## 5. Mapped device/order-code identifiers

The ten-vendor enrichment currently produces:

| Metric | Count |
|---|---:|
| Candidate mapping records | 5,796 |
| Unique `(vendor, identifier)` pairs | 5,796 |
| Referenced OpenOCD target CFG files | 55 |
| CMSIS device-name identifiers | 3,983 |
| Ordering-pattern identifiers | 1,813 |
| Verified `exact_part_number` classification | Pending Phase 1 reclassification |

The 5,796 count is not an exact orderable-Part-Number count. Some CMSIS device names may be orderable part numbers, but that cannot be asserted until deterministic vendor-specific classification promotes them to `identifier_kind = exact_part_number`. Ordering patterns must remain visibly distinct.

## 6. Candidate mappings by vendor

| Vendor | Candidate identifiers |
|---|---:|
| STMicroelectronics | 2,333 |
| Infineon | 1,480 |
| Silicon Labs | 1,147 |
| Nuvoton | 492 |
| Microchip | 149 |
| NXP | 113 |
| Texas Instruments | 56 |
| Nordic Semiconductor | 19 |
| Espressif | 7 |
| Renesas | 0 |
| **Total** | **5,796** |

Renesas remains in the ten-vendor research scope, but its current authoritative identifiers do not have a mapping that meets the candidate-export rules for the available OpenOCD target profiles.

## 7. CPU architectures of the 5,796 mapped identifiers

| CPU architecture | Mapped identifiers |
|---|---:|
| ARM Cortex-M | 5,789 |
| RISC-V | 4 |
| Xtensa | 3 |
| **Total** | **5,796** |

These counts describe the current nine vendors with exported candidate mappings, not every architecture supported by OpenOCD. The difference between the broad CFG table and this mapped-identifier table is intentional: the DFP/ESP-IDF enrichment currently covers only the first ten vendor groups and only relationships accepted for candidate export.

## 8. Reproduction and acceptance rules

The implementation should reproduce this baseline from versioned inputs and fail validation when totals drift without an explicit catalog update. At minimum it must:

1. Recursively enumerate `tcl/target/**/*.cfg`.
2. Record the exact OpenOCD commit.
3. Extract direct CPU target types and statically resolvable target includes.
4. Preserve multi-architecture membership rather than forcing one CPU per CFG.
5. Keep helper/non-CPU CFG files separate.
6. Join mapped identifiers to target CFG paths and reject missing paths.
7. Count CMSIS device names, ordering patterns, and exact part numbers separately.
8. Produce vendor and CPU-architecture totals with consistency checks.
9. Require `sum(vendor mappings) = sum(mapped identifier architectures) = exported mapping records` for the current one-architecture-per-exported-identifier dataset.
