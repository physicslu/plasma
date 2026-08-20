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
- First automated expansion: 1,023 identifiers across 36 additional target configurations
- First automated expansion identifier kinds: 893 CMSIS device names and 130 ordering patterns
- First automated expansion sources: 27 pinned PDSC files
- Expansion targets awaiting a source adapter/rule: 69
- Helper/alias or external-Flash-only expansion targets deferred: 9

## User-facing selection

```text
Search part number
or
Vendor → Series → Part number
```

The target seed establishes **Vendor → Series → OpenOCD target**. The first enrichment adds STMicroelectronics, NXP, Microchip, Nordic Semiconductor, and Texas Instruments. The second adds Infineon, Espressif, Silicon Labs, Nuvoton, and Renesas. CMSIS DFP is used where available; Espressif device identifiers come from the official ESP-IDF SoC tree. Every mapping remains `not_validated` until Plasma hardware qualification is complete.

## Columns

| Column | Meaning |
|---|---|
| `vendor` | User-facing manufacturer name |
| `series` | Simplified product family/series |
| `display_name` | Human-readable target name |
| `target_config` | OpenOCD configuration path |
| `device_type` | MCU, Wireless MCU, SoC, FPGA SoC, etc. |
| `classification_status` | Auto-classified, Needs review, or Internal/helper |
| `part_number` | Reserved for authoritative full part number enrichment |

## Usage rules

1. Do not show `Internal/helper` records in the Plasma chip selector.
2. Do not claim that an `Auto-classified` target is production-supported.
3. Enrich exact part numbers from manufacturer sources and map each part to one target record.
4. Production mode must show only part profiles with `production_validated` status.
5. Engineering mode may expose unvalidated mappings with a clear warning.
6. The user-facing selector should use the `*_mapped.csv` files, not the full research files.
7. Generic family aliases such as `Generic_M051_Series` are excluded from the user-facing mapped table.
8. A target must have a known usable OpenOCD Flash programming backend before its devices can enter the user-facing mapped table. The current rule excludes 24 STM32N6 and 12 TLE987x identifiers. The seven Espressif identifiers require the official `openocd-esp32` distribution rather than the pinned upstream OpenOCD build.

## Known limitations

- Filename-based vendor mapping is heuristic and requires review.
- A single target config can cover many part numbers.
- Package, flash size, voltage, silicon ID, and socket data are not reliably available from target filenames.
- TLE987x and STM32N6 identifiers remain in the full research files as unmapped records because their current target CFG files do not configure a Flash bank/driver.
- The current mapped schema does not yet carry the required backend distribution/version per record; Espressif's vendor-fork requirement must be added before canonical import.
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
- `openocd-parts-expanded.csv` / `.json`: deterministic PDSC-to-Target mappings from the current execution batch.
- `openocd-expansion-outcomes.csv`: one terminal current-run outcome for each of the 114 candidates.
- `source-manifest.json`: Pack Index and PDSC versions, URLs, and SHA-256 provenance.
- `mapping-rules.json`: exported deterministic rule set used by the generator.
- `expansion-report.md`: current execution totals and status interpretation.

The generator can also produce JSON and full research exports containing unmapped identifiers. Those larger or duplicate source-audit artifacts are intentionally not checked in here; the selectable mapped CSV tables are the checked-in part-number research documents.
