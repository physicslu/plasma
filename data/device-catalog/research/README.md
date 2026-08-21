# Plasma OpenOCD Target Catalog — Seed v1

This research catalog recursively converts OpenOCD `tcl/target/**/*.cfg` entries into a simple user-facing seed taxonomy, then enriches MCU vendors from official device sources. It is not a production-support claim or the canonical Phase 1 catalog artifact.

## Scope

- Source commit: `56b8d93fbe61a78dc903d770820d6d896b6d8134`
- Generated: 2026-08-20
- Target configuration files: 399
- Auto-classified: 325
- Needs manual review: 51
- Internal/helper configurations: 23
- CMSIS Device Family Packs parsed: 375
- Official CMSIS device names found: 4,403
- Candidate OpenOCD mappings: 2,646
- Unmapped research records: 1,757
- Next-five official device identifiers: 4,707
- Next-five candidate mappings: 3,114 selectable device identifiers
- Next-five unmapped research records: 1,588
- Selectable mapped identifiers: 5,760
- Selectable target configurations: 53
- Excluded for missing configured Flash bank/driver: 36 identifiers across 2 target configurations
- MCU/Wireless MCU expansion candidates evaluated: 114
- Current automated expansion: 1,931 identifiers across 99 additional target configurations
- Current expansion identifier kinds: 1,616 device names, 167 exact manufacturer ordering part numbers, and 148 ordering patterns
- Current expansion sources: 58 pinned PDSCs, 16 manufacturer/Arm MCU sources, 5 OpenOCD Flash-driver tables, and 7 exact-MCU OpenOCD target definitions; no board sources
- Expansion targets awaiting a source adapter/rule: 0
- Helper/alias, external-only, Flashless, or invalid-TAP expansion targets deferred: 15
- Canonical selectable identifiers after cross-catalog deduplication: 7,657
- Canonical MCU vendors: 19
- Manufacturer MCU families preserved: 310
- Simplified Plasma series preserved: 141
- Manufacturer MCU subfamilies when available: 862
- Selectable identifiers without an optional subfamily: 908
- Canonical selectable target configurations: 152
- Cross-catalog target conflicts resolved: 34 STM32H7R/S identifiers
- Canonical CPU architectures: ARM Cortex-M, ARM7TDMI, ARM966E-S, AVR, MIPS32, RISC-V, and Xtensa

## User-facing selection

```text
Start typing a chip part number
    -> exact match first
    -> then prefix matches
    -> then other partial matches
    -> show vendor, original manufacturer family, and Plasma series beside each result
```

Part-number autocomplete is the primary user interaction. It must not require a customer to know the vendor, manufacturer family, subfamily, or Plasma series before searching. Matching should be case-insensitive and prefer exact identifier matches over prefix and other partial matches. Vendor filtering and classification text are optional refinements/result context, not mandatory selection steps.

The target seed establishes **Vendor → Plasma series → OpenOCD target**, while manufacturer sources preserve their original **Family → Subfamily** hierarchy. The canonical selector catalog retains both independently because many manufacturer families can map to the same simplified Plasma series, while some OpenOCD target series are narrower than a manufacturer family. `subfamily` is optional and must not hide an otherwise selectable device. The first enrichment adds STMicroelectronics, NXP, Microchip, Nordic Semiconductor, and Texas Instruments. The second adds Infineon, Espressif, Silicon Labs, Nuvoton, and Renesas. CMSIS DFP is used where available; Espressif device identifiers come from the official ESP-IDF SoC tree. Every canonical mapping remains `mapping_candidate` and `not_verified` until physical qualification produces separate evidence.

## Target-seed columns

| Column | Meaning |
|---|---|
| `vendor` | User-facing manufacturer name |
| `series` | Simplified product family/series |
| `display_name` | Human-readable target name |
| `target_config` | OpenOCD configuration path |
| `device_type` | MCU, Wireless MCU, SoC, FPGA SoC, etc. |
| `classification_status` | Auto-classified, Needs review, or Internal/helper |
| `part_number` | Reserved for authoritative full part number enrichment |

## Canonical selector columns

| Column | Meaning |
|---|---|
| `vendor` | User-facing manufacturer name |
| `family` | Original manufacturer-defined MCU family |
| `subfamily` | Original manufacturer-defined MCU subfamily, or empty when unavailable |
| `plasma_series` | Simplified Plasma/OpenOCD target grouping |
| `part_number` | Searchable manufacturer/device identifier; interpret according to `identifier_kind` |
| `identifier_kind` | Exact manufacturer part number, vendor/CMSIS device name, or ordering pattern |
| `cpu_architectures` | JSON list of CPU architectures supported by the mapped Target CFG |
| `target_config` | Deterministically selected OpenOCD target configuration |
| `openocd_distribution` | Required upstream OpenOCD or vendor-specific backend distribution |
| `mapping_status` | Backend mapping state; imported candidates are not hardware validation |
| `validation_status` | Physical-validation state; this research snapshot remains `not_verified` |
| `catalog_origin` | Source-specific research catalog from which the selected record originated |

## Usage rules

1. Do not show `Internal/helper` records in the Plasma chip selector.
2. Do not claim that an `Auto-classified` target is production-supported.
3. Enrich exact part numbers from manufacturer sources and map each part to one target record.
4. Production mode must show only part profiles with `production_validated` status.
5. Engineering mode may expose unvalidated mappings with a clear warning.
6. The user-facing selector should use `openocd-parts-canonical.csv`, not the overlapping source-specific research files.
7. Generic family aliases such as `Generic_M051_Series` are excluded from the user-facing mapped table.
8. A target must have a known usable OpenOCD Flash programming backend before its devices can enter the user-facing mapped table. The current rule excludes 24 STM32N6 and 12 TLE987x identifiers. The seven Espressif identifiers require the official `openocd-esp32` distribution rather than the pinned upstream OpenOCD build.
9. A device that exposes more than one CPU architecture, such as RP2350, remains one canonical identifier and lists every architecture supported by its Target CFG.
10. When a baseline family CFG overlaps a narrower newly mapped CFG, prefer the narrower mapping and retain the decision in `openocd-duplicate-resolutions.csv`.
11. Search by chip identifier first; never require users to choose a manufacturer family or Plasma series before finding their device.
12. Preserve the original manufacturer family/subfamily separately from the simplified Plasma series; do not rewrite either classification into the other.

## Known limitations

- Filename-based vendor mapping is heuristic and requires review.
- A single target config can cover many part numbers.
- Package, flash size, voltage, silicon ID, and socket data are not reliably available from target filenames.
- TLE987x and STM32N6 identifiers remain in the full research files as unmapped records because their current target CFG files do not configure a Flash bank/driver.
- Historical source-specific mapped CSVs do not carry the required backend distribution; use the canonical CSV, which explicitly records Espressif's `openocd-esp32` requirement.
- Historical vendor names and acquisitions require a deliberate normalization policy.

## Files

- `plasma_openocd_target_catalog.csv`: spreadsheet/import form.
- `plasma_openocd_target_catalog.json`: structured seed catalog with source metadata.
- `generate_openocd_target_catalog.py`: reproducible generator for future OpenOCD updates.
- `plasma_openocd_parts_top5_mapped.csv`: simplified five-vendor candidate table for review/UI prototyping.
- `plasma_openocd_parts_next5_mapped.csv`: simplified Infineon, Espressif, Silicon Labs, Nuvoton, and Renesas candidate table.
- `enrich_cmsis_parts.py`: reproducible CMSIS DFP enrichment tool.
- `expand_openocd_parts.py`: fail-closed generator for the 114-target MCU-first expansion backlog.
- `openocd-target-capabilities.csv` / `.json`: resolved include graph and Flash capability for all 114 candidates.
- `openocd-parts-expanded.csv` / `.json`: deterministic authoritative-source-to-Target mappings from the current execution batch.
- `openocd-parts-canonical.csv`: deduplicated Plasma import/selector table combining the existing mapped identifiers and current expansion.
- `openocd-duplicate-resolutions.csv`: auditable target-selection decisions for identifiers appearing in both baseline and expansion catalogs.
- `openocd-expansion-outcomes.csv`: one terminal current-run outcome for each of the 114 candidates.
- `source-manifest.json`: Pack Index, PDSC, pinned MCU vendor SDK/product sources, exact-chip OpenOCD target definitions, Flash-driver tables, versions, URLs, and SHA-256 provenance; board sources are excluded.
- `mapping-rules.json`: exported deterministic rule set used by the generator.
- `expansion-report.md`: current execution totals and status interpretation.
- `validate_openocd_expansion.py`: offline invariants for source provenance, CPU architectures, aliases, source-aware rules, and cross-catalog uniqueness.

The generator can also produce JSON and full research exports containing unmapped identifiers. Those larger or duplicate source-audit artifacts are intentionally not checked in here; the selectable mapped CSV tables are the checked-in part-number research documents.
