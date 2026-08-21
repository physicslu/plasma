# OpenOCD Part-Number Expansion Plan

Status: 114-target MCU-first expansion completed; all selectable CFG candidates resolved

## 1. Goal and boundary

Expand the 344 OpenOCD target CFG files that have not yet been researched into device identifiers, starting with MCU targets that declare a usable Flash bank/driver.

The 344 count preserves the original research boundary:

```text
399 recursive target CFG files
- 55 CFG files already researched for identifiers
= 344 CFG files not yet expanded
```

Two of the 55 researched CFG files, `stm32n6x.cfg` and `infineon/tle987x.cfg`, are no longer selectable because they do not configure a Flash bank/driver. They remain part of the researched set rather than being counted again in the 344-file expansion backlog.

CPU debug access alone is insufficient. A device can become a selectable mapping candidate only when OpenOCD has a compatible programming path for its non-volatile memory. Static discovery is evidence of declared capability, not proof of successful Plasma or real-device programming.

The customer-selectable object is always an MCU chip, never a development board, evaluation kit, module, or assembled PCB. Expansion sources must identify the MCU itself through a device pack, a manufacturer MCU document, or an explicit supported-part table in the pinned OpenOCD Flash driver. Board definitions and board inventories are not accepted as MCU part-number sources.

## 2. Initial automated triage

The OpenOCD snapshot at commit `56b8d93fbe61a78dc903d770820d6d896b6d8134` produces this first-pass backlog:

| Backlog class | Target CFG files |
|---|---:|
| Not yet expanded | 344 |
| Statically resolves at least one `flash bank` declaration | 124 |
| MCU or Wireless MCU with a Flash declaration | **114** |
| Flash-declaring non-MCU targets, deferred | 10 |
| No statically resolved Flash declaration, deferred | 220 |

The first expansion program therefore starts with 114 CFG candidates: 110 MCU and 4 Wireless MCU target files. These are candidates for deeper inspection, not 114 confirmed independently selectable families. Common/base CFG files, aliases, virtual banks, external-only Flash, and overlapping family files must be normalized before identifier export.

Current execution checkpoint:

| Result | Count |
|---|---:|
| MCU/Wireless MCU CFG candidates evaluated | 114 |
| CFG files with deterministic authoritative-source mappings | 99 |
| Unique expansion device identifiers mapped | 1,931 |
| CMSIS/vendor device names | 1,616 |
| Exact manufacturer ordering part numbers | 167 |
| Ordering patterns | 148 |
| Pinned PDSC sources parsed | 58 |
| Pinned vendor/Arm MCU SDK, device-database, or product sources parsed | 16 |
| Pinned OpenOCD MCU Flash-driver part tables parsed | 5 |
| Pinned OpenOCD exact-MCU target definitions parsed | 7 |
| Helper/alias, external-only, Flashless, or invalid-TAP targets deferred | 15 |
| Flash-capable targets awaiting an adapter/rule | **0** |
| Baseline/expansion target conflicts resolved | 34 |
| Canonical unique device identifiers | 7,657 |
| Canonical MCU vendors | 19 |
| Original manufacturer MCU families retained | 310 |
| Simplified Plasma target series retained | 141 |
| Optional manufacturer MCU subfamilies retained | 862 |
| Selectable identifiers without an optional subfamily | 908 |
| Canonical unique target CFG files | 152 |

The 1,931 expansion identifiers are `mapping_candidate` and `not_verified`; they do not increase the engineering-verified or production-qualified count. Combining the 5,760 baseline identifiers with the expansion and collapsing 34 overlapping STM32H7R/S identifiers produces 7,657 canonical unique device identifiers. Every canonical record retains both its original manufacturer family and its simplified Plasma series; manufacturer subfamily is preserved when available. Future customer lookup must be live and identifier-first: exact matches rank before prefix and partial matches, while manufacturer/family/series remain supporting context rather than prerequisite selection steps. Re-run `expand_openocd_parts.py` from the pinned OpenOCD checkout and source index to reproduce the checkpoint, then run `validate_openocd_expansion.py` offline.

The 15 deferred CFGs consist of 11 helper/alias definitions, one external-Flash-only configuration, one Flashless LPC2460 configuration, and two configurations with unresolved `0xffffffff` JTAG TAP IDs. None is presented as a selectable MCU mapping.

| Canonical CPU architecture | Target CFG files | Device identifiers |
|---|---:|---:|
| ARM Cortex-M | 122 | 7,442 |
| ARM7TDMI | 13 | 47 |
| ARM966E-S | 2 | 12 |
| AVR | 3 | 3 |
| MIPS32 | 1 | 128 |
| RISC-V | 9 | 24 |
| Xtensa | 3 | 3 |

RP2350 supports both ARM Cortex-M and RISC-V in one Target CFG. Therefore architecture subtotals count its two identifiers in both CPU families, while the canonical table contains each device only once.

## 3. Priority waves

### Wave 0 — Capability inventory and fail-closed gate (complete for the 114 candidates)

Before adding identifiers:

1. Parse each CFG and its statically resolvable `source [find ...]` include graph.
2. Extract CPU target type, transport, DAP/TAP relationship, Flash bank, concrete Flash driver, base address, and target relationship.
3. Confirm the referenced Flash driver is built by the selected OpenOCD distribution.
4. Distinguish concrete Flash drivers from `virtual` aliases.
5. Mark internal/common/base CFG files so they cannot appear as duplicate customer choices.
6. Separate internal Flash, external NOR/QSPI/SPI Flash, OTP/configuration memory, and EEPROM-like banks.
7. Record the required OpenOCD distribution and version; upstream OpenOCD and vendor forks are separate backends.

Output states:

```text
flash_driver_declared
flash_driver_missing
external_flash_only
debug_only
helper_or_alias
needs_review
```

Only `flash_driver_declared` proceeds automatically to MCU identifier expansion.

### Wave 1 — Reuse existing vendor-source pipelines (complete)

Start with the 82 Flash-declaring MCU CFG candidates belonging to vendor groups already handled by the current DFP/PDSC enrichment pipeline.

| Vendor group | CFG candidates |
|---|---:|
| Microchip | 25 |
| NXP | 25 |
| STMicroelectronics | 17 |
| Texas Instruments | 7 |
| Silicon Labs | 5 |
| Nuvoton | 2 |
| Infineon | 1 |
| **Total** | **82** |

Process these in batches of 10–20 CFG files. Prefer modern MCU families with current structured vendor packs, then handle legacy families whose identifiers may require archived packs or product tables.

The first PDSC batch mapped 36 CFG files across Microchip, NXP, STMicroelectronics, Texas Instruments, and Nuvoton. Subsequent batches added official vendor-direct PDSCs, pinned manufacturer SDK/product documents, Arm Keil chip databases, explicit OpenOCD driver part tables, and exact-MCU target definitions. Together they resolve every eligible MCU target in both vendor waves; the outcome table is authoritative for current per-target progress.

Each vendor batch must add deterministic mapping fixtures. A filename or family-name substring alone is not sufficient when multiple CFG files overlap.

### Wave 2 — Add new vendor-source adapters (complete)

After Wave 1 rules are stable, process the remaining 32 Flash-declaring MCU CFG candidates.

| Vendor group | CFG candidates |
|---|---:|
| Analog Devices | 15 |
| Bouffalo Lab | 4 |
| Cypress/Fujitsu | 3 |
| Geehy | 3 |
| GigaDevice | 2 |
| Raspberry Pi | 2 |
| Artery | 1 |
| Holtek | 1 |
| XMOS | 1 |
| **Total** | **32** |

Use an official structured device pack or machine-readable product source when available. If a vendor has no suitable structured source, retain the CFG as a capability record and put identifier extraction into the exception queue; do not guess complete part numbers from a family name.

The completed batches map Analog Devices/MAXIM, Artery, Bouffalo Lab, Cypress/Fujitsu, Geehy, GigaDevice, Holtek, Infineon, Microchip, NIIET, NXP, Nuvoton, Raspberry Pi, Silicon Labs, STMicroelectronics, Texas Instruments, and XMOS. OpenOCD driver tables directly establish AT32F4, PSoC 5LP, K1921VK01T, LPC29xx, and NHS31xx compatibility. Manufacturer documents constrain ADuC70xx to the driver's 62 KB Flash geometry, EM358x to its configured 512 KB geometry, and STM32W108 to the configured 64 KB STM32W108C8. Arm Keil device records cover legacy STR7/STR9 and SiM3 targets; Nuvoton's own SoC definitions establish NPCX7 identifiers. No development-board definitions or inventories are consulted, and no eligible CFG remains `source_adapter_pending`.

### Wave 3 — Deferred targets

Do not expand the remaining 230 CFG files into the normal MCU selector during the first program:

- 220 do not statically resolve a Flash declaration;
- 10 declare Flash but are classified as SoC, DSP, FPGA/SoC, or Unknown rather than MCU/Wireless MCU.

Revisit them through separate SoC, DSP, external-memory, legacy-target, and vendor-fork workstreams. A vendor tool or fork may later provide a valid programming backend, but that must be represented as a separate versioned Programming Profile rather than silently attributed to upstream OpenOCD.

## 4. Per-target expansion workflow

For every CFG admitted from Wave 1 or Wave 2:

1. Resolve the concrete Target CFG and Flash driver.
2. Identify the authoritative vendor source and record its version and license metadata.
3. Extract device names, ordering patterns, exact part numbers, packages, and memory sizes without conflating those identifier kinds.
4. Normalize vendor names while preserving the original manufacturer family/subfamily, separately deriving the Plasma series from the selected Target CFG.
5. Apply a versioned vendor-specific mapping rule.
6. Reject ambiguous many-to-many matches into an exception queue.
7. Deduplicate aliases and common/base CFG relationships.
8. Check Flash size/geometry, device-ID constraints, transport, target voltage metadata when available, and relevant OpenOCD configuration parameters.
9. Export accepted records as `mapping_candidate` and `not_verified` only.
10. Add deterministic fixtures showing accepted, rejected, and ambiguous examples for the rule.

No row-by-row manual approval should be required for deterministic matches. Human work is limited to new source formats, unresolved conflicts, licensing decisions, and real-hardware sample handling.

## 5. Selectable-record acceptance criteria

A record may enter the Engineering-mode selectable catalog only when all of these are true:

- authoritative device identifier and source provenance exist;
- identifier kind is explicit;
- one deterministic Target CFG mapping exists;
- a concrete Flash driver and intended Flash bank exist;
- required OpenOCD distribution/version is recorded;
- the Target CFG path exists in the pinned OpenOCD snapshot;
- the record is not a helper/common duplicate;
- automated schema, duplicate, mapping, and target-path checks pass.

This gate establishes only software-declared programmability. It does not create `engineering_verified`, Socket compatibility, or production evidence. Those states still require the physical validation workflow.

## 6. Planned outputs

```text
data/device-catalog/research/openocd-target-capabilities.csv
data/device-catalog/research/openocd-target-capabilities.json
data/device-catalog/research/openocd-parts-expanded.csv
data/device-catalog/research/openocd-parts-expanded.json
data/device-catalog/research/openocd-parts-canonical.csv
data/device-catalog/research/openocd-duplicate-resolutions.csv
data/device-catalog/research/openocd-expansion-outcomes.csv
data/device-catalog/research/source-manifest.json
data/device-catalog/research/mapping-rules.json
data/device-catalog/research/expansion-report.md
data/device-catalog/research/validate_openocd_expansion.py
```

The report for every batch must include:

- CFG files evaluated, accepted, deferred, and rejected;
- identifiers by vendor and identifier kind;
- concrete Flash drivers and transports;
- duplicate/alias collapses;
- ambiguous and unmapped records;
- source and license exceptions;
- changed totals relative to the previous snapshot.

## 7. Completion criteria

The MCU-first expansion is complete when all 114 initial MCU/Wireless MCU candidates have a deterministic outcome:

```text
selectable mapping candidate
or
documented deferred/rejected reason
```

Counts must be reproducible from pinned inputs. A changed OpenOCD, DFP, PDSC, vendor source, mapping rule, or backend distribution creates a new catalog snapshot rather than silently changing the existing one.
