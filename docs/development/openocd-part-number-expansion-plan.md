# OpenOCD Part-Number Expansion Plan

Status: planned expansion after the initial ten-vendor research catalog

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

## 3. Priority waves

### Wave 0 — Capability inventory and fail-closed gate

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

### Wave 1 — Reuse existing vendor-source pipelines

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

Each vendor batch must add deterministic mapping fixtures. A filename or family-name substring alone is not sufficient when multiple CFG files overlap.

### Wave 2 — Add new vendor-source adapters

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
4. Normalize vendor/family names while preserving original spelling and provenance.
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
data/device-catalog/research/source-manifest.json
data/device-catalog/research/mapping-rules.json
data/device-catalog/research/expansion-report.md
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
