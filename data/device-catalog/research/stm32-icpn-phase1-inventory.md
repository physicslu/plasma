# STM32 ICPN — Phase 1 Inventory Analysis

**Source of record:** `data/device-catalog/research/openocd-parts-canonical.csv`
**Analysis method:** single deterministic pass — the source CSV was opened and parsed exactly once; every figure in this report is taken from that one parse. No web research and no manual count estimation were used.
**Git context at run:** branch `research/stm32-icpn-phase1`, HEAD `43541ef7`.
**Working tree at run:** clean (`git status --short` empty) before this report was created.

---

## 0. Evidence-tier convention (read before the numbers)

This report keeps three non-equivalent kinds of evidence strictly separate and does not conflate them:

- **Tier A — Exact commercial ICPN / IC Part Number evidence.** The `part_number` cell is a commercial
  manufacturer part number, flagged by `identifier_kind == "manufacturer_part_number"`.
- **Tier B — Family / series classification.** The `family`, `plasma_series`, `subfamily` text columns, plus
  the wildcard-bearing `part_number` cells of `identifier_kind = ordering_pattern` / `cmsis_device_name`.
- **Tier C — OpenOCD programming-capability evidence.** `target_config` (OpenOCD `.cfg` path) together with
  `openocd_distribution`, `mapping_status`, `validation_status`.

**Hard limits observed in this report (no exception):**

1. No commercial ICPN / IC Part Number is *inferred* for any STM32 row that is not already
   `identifier_kind == "manufacturer_part_number"`. Because that count is 0 (§2.1), no commercial part
   number is asserted for any STM32 device.
2. No claim of completeness against the STM32 commercial product universe is made. The catalog self-describes
   as a derived, expanded, candidate and unverified mapping (`openocd-parts-expanded.csv`;
   `mapping_candidate`; `not_verified`).
3. No claim that one OpenOCD `.cfg` equals exactly one commercial STM32 series is made. The counts and the
   available data do not establish that bijection (§2.3).
4. No web research. All figures derive solely from the single CSV parse.

---

## 1. Method and definitions

- Whole-catalog parse of `openocd-parts-canonical.csv`. Header columns:
  `vendor, family, subfamily, plasma_series, part_number, identifier_kind, cpu_architectures, target_config, openocd_distribution, mapping_status, validation_status, catalog_origin`.
- A **row** is a non-blank CSV record (fully blank lines, if any, are ignored).
- **STMicroelectronics** row: `vendor` contains `stmicro` (case-insensitive; also `st` / `stmicroelectronics`).
- **STM32-classified** row: case-insensitive substring `stm32` in any of `family / subfamily / plasma_series / part_number / target_config` (fallback: any cell). The stricter rule "family or plasma_series starts with `stm32`" yields the identical count (2,411), so both rules agree and the classification is stable.
- **Exact** = `identifier_kind == "manufacturer_part_number"` (case-insensitive).
- **Non-exact** = any `identifier_kind` other than `manufacturer_part_number` (i.e. `cmsis_device_name`, `ordering_pattern`, or blank).
- **Subfamily blank / non-blank** tracked explicitly, with the sentinel `<blank>` for an empty cell.

---

## 2. Headline findings

### 2.1 Tier A — Exact commercial ICPN / IC Part Number evidence

| Metric | Count |
|---|---:|
| Whole-catalog exact `manufacturer_part_number` rows | 167 |
| STM32-classified exact `manufacturer_part_number` rows | 0 |
| STM32-classified exact rows with a non-blank `part_number` | 0 |

**Conclusion (headline).** This Phase 1 inventory contains **zero** exact commercial ICPN / IC Part Number
evidence for STM32. Every STM32 row is a *non-exact* identifier:

- `ordering_pattern` — 1,870 rows
- `cmsis_device_name` — 541 rows
- `manufacturer_part_number` — 0 rows (subtotals to 2,411, the STM32-classified total)

All 167 exact-MPN rows in the whole catalog therefore belong to **non-STM32** devices within this file. No
commercial part number is asserted or inferred for any STM32 device here.

### 2.2 Tier B — Family / series classification

| Metric | Count |
|---|---:|
| STMicroelectronics rows (whole vendor set) | 2,420 |
| STMicroelectronics rows *not* STM32-classified (excluded from this tier) | 9 |
| STM32-classified rows | 2,411 |
| Distinct `family` values | 22 |
| Distinct `plasma_series` values | 23 |
| Distinct `subfamily` values (including blank) | 204 |
| Distinct `subfamily` values (non-blank) | 203 |
| `subfamily` blank rows / non-blank rows | 1 / 2,410 |

Granularity observations (from §3 data):

- `plasma_series` is finer than `family` (23 vs 22). Example: `STM32WBA5X`, `STM32WBA6X`, `STM32WBA2X` are
  separate series that collapse into the single `STM32WBA Series` family; `STM32H7` series = 200 whereas the
  family level splits it into `STM32H7 Series` = 166 + `STM32H7RS Series` = 34.
- There is one `family` value of exactly `STM32` (1 row) with no finer classification — a fallback bucket,
  not a commercial series.
- `family`, `plasma_series`, and `subfamily` cells (and the `ordering_pattern` / `cmsis_device_name`
  `part_number` cells, some of which contain wildcards such as `x`) are **text classifications**, not
  commercial ICPN.
- Full enumerations: §3.3 (`family`), §3.4 (`plasma_series`), §3.6 (`subfamily`).

### 2.3 Tier C — OpenOCD programming-capability evidence

| Metric | Value |
|---|---|
| STM32 rows total | 2,411 |
| `openocd_distribution` across all STM32 rows | `upstream-openocd` (2,411 / 2,411) |
| `mapping_status` across all STM32 rows | `mapping_candidate` (2,411 / 2,411) |
| `validation_status` across all STM32 rows | `not_verified` (2,411 / 2,411) |
| Distinct `target_config` (OpenOCD `.cfg`) values | 24 |
| Blank `target_config` rows | 0 |

Shape of the mapping — **not** a bijection:

- 2,411 STM32 rows map onto only **24** distinct `.cfg` targets, **23** distinct `plasma_series`, and **22**
  distinct `family` values. Many rows collapse onto a single `.cfg` (e.g. `tcl/target/stm32f4x.cfg` serves
  many F4 subfamilies). The distinct counts differ (24 / 23 / 22) and this single table provides no join that
  proves a 1:1 correspondence.
- **Therefore one OpenOCD `.cfg` is NOT equated with exactly one commercial STM32 series.**
- Capability status is **candidate and not verified**: every STM32 row is a `mapping_candidate` with
  `validation_status = not_verified`. This is candidate programming support, *not* validated programming support.

---

## 3. Deterministic statistics (single parse)

### 3.1 Whole catalog

| Metric | Value |
|---|---:|
| Total catalog rows (non-blank) | 7,657 |
| Non-exact rows (whole catalog) | 7,490 |
| STMicroelectronics rows | 2,420 |

`identifier_kind` counts over the whole catalog (sum = 7,657):

| identifier_kind | whole-catalog count |
|---|---:|
| cmsis_device_name | 5,559 |
| ordering_pattern | 1,931 |
| manufacturer_part_number | 167 |

### 3.2 STM32 subset (n = 2,411)

| Metric | Value |
|---|---:|
| STM32-classified rows | 2,411 |
| `identifier_kind` = ordering_pattern | 1,870 |
| `identifier_kind` = cmsis_device_name | 541 |
| `identifier_kind` = manufacturer_part_number | 0 |
| Exact STM32 rows (non-blank `part_number`) | 0 |
| Non-exact STM32 rows | 2,411 |
| Distinct `target_config` | 24 (0 blank) |
| `openocd_distribution` | upstream-openocd (2,411) |
| `mapping_status` | mapping_candidate (2,411) |
| `validation_status` | not_verified (2,411) |

Non-exact breakdown:

- Whole catalog (7,490): `cmsis_device_name` 5,559 + `ordering_pattern` 1,931.
- STM32 subset (2,411, i.e. all STM32 rows): `ordering_pattern` 1,870 + `cmsis_device_name` 541.

### 3.3 STM32 distinct `family` — 22 values (rows descending)

| family | rows |
|---|---:|
| STM32L4 Series | 255 |
| STM32F4 Series | 211 |
| STM32G4 Series | 183 |
| STM32G0 Series | 182 |
| STM32U3 Series | 171 |
| STM32H7 Series | 166 |
| STM32L0 Series | 166 |
| STM32U5 Series | 162 |
| STM32L1 Series | 132 |
| STM32F7 Series | 123 |
| STM32F0 Series | 111 |
| STM32C0 Series | 95 |
| STM32F1 Series | 95 |
| STM32F3 Series | 90 |
| STM32WBA Series | 61 |
| STM32U0 Series | 48 |
| STM32F2 Series | 47 |
| STM32L5 Series | 38 |
| STM32H7RS Series | 34 |
| STM32WB Series | 23 |
| STM32WL Series | 17 |
| STM32 | 1 |

### 3.4 STM32 distinct `plasma_series` — 23 values (rows descending)

| plasma_series | rows |
|---|---:|
| STM32L4 | 255 |
| STM32F4 | 211 |
| STM32H7 | 200 |
| STM32G4 | 183 |
| STM32G0 | 182 |
| STM32U3 | 171 |
| STM32L0 | 166 |
| STM32U5 | 162 |
| STM32L1 | 132 |
| STM32F7 | 123 |
| STM32F0 | 111 |
| STM32C0 | 95 |
| STM32F1 | 95 |
| STM32F3 | 90 |
| STM32U0 | 48 |
| STM32F2 | 47 |
| STM32L5 | 38 |
| STM32WBA5X | 34 |
| STM32WBX | 23 |
| STM32WBA6X | 19 |
| STM32WLX | 17 |
| STM32WBA2X | 8 |
| STM32W108 | 1 |

### 3.5 STM32 sorted unique `target_config` — 24 values (0 blank)

```
tcl/target/stm32c0x.cfg
tcl/target/stm32f0x.cfg
tcl/target/stm32f1x.cfg
tcl/target/stm32f2x.cfg
tcl/target/stm32f3x.cfg
tcl/target/stm32f4x.cfg
tcl/target/stm32f7x.cfg
tcl/target/stm32g0x.cfg
tcl/target/stm32g4x.cfg
tcl/target/stm32h7rsx.cfg
tcl/target/stm32h7x.cfg
tcl/target/stm32l0.cfg
tcl/target/stm32l1.cfg
tcl/target/stm32l4x.cfg
tcl/target/stm32l5x.cfg
tcl/target/stm32u0x.cfg
tcl/target/stm32u3x.cfg
tcl/target/stm32u5x.cfg
tcl/target/stm32w108xx.cfg
tcl/target/stm32wba2x.cfg
tcl/target/stm32wba5x.cfg
tcl/target/stm32wba6x.cfg
tcl/target/stm32wbx.cfg
tcl/target/stm32wlx.cfg
```

### 3.6 STM32 `subfamily` — 204 distinct including 1 blank (203 non-blank)

Blank / non-blank row split: **1 blank / 2,410 non-blank**. The single blank `subfamily` row also appears in
the `family = "STM32"` bucket (§3.3). The 203 non-blank distinct values, with row counts (descending), are:

```
STM32L151:55 STM32L152:53 STM32G0B1:43 STM32L5x2:38 STM32U535:35 STM32U375:32 STM32C071:30 STM32U356:30 STM32U3B5:30 STM32U575:30 STM32F101:29 STM32F103:29 STM32G0C1:29 STM32H7A3:29 STM32G431:27 STM32G473:27 STM32G474:25 STM32L4P5:25 STM32F303:24 STM32F469:24 STM32U073:24 STM32U595:23 STM32F302:22 STM32F429:22 STM32G411:22 STM32L072:22 STM32U335:22 STM32F401:21 STM32G031:21 STM32G071:20 STM32L071:20 STM32F100:19 STM32G491:19 STM32L412:19 STM32L496:19 STM32L476:18 STM32F051:17 STM32F205:17 STM32G471:17 STM32L162:17 STM32C091:16 STM32C092:16 STM32F207:16 STM32F412:16 STM32F479:16 STM32F746:16 STM32H742:16 STM32H743:16 STM32L431:16 STM32L4Q5:16 STM32U031:16 STM32U385:16 STM32F439:15 STM32H725:15 STM32H7B3:15 STM32L052:15 STM32L433:15 STM32L452:15 STM32U366:15 STM32U3C5:15 STM32U585:15 STM32F413:14 STM32F765:14 STM32F767:14 STM32G041:14 STM32L011:14 STM32L031:14 STM32L051:14 STM32L073:14 STM32L4R5:14 STM32U545:14 STM32F042:13 STM32F072:13 STM32G051:13 STM32G061:13 STM32WB55:13 STM32C031:12 STM32C051:12 STM32F373:12 STM32F3x4:12 STM32F3x8:12 STM32F446:12 STM32F723:12 STM32L451:12 STM32L4A6:12 STM32F091:11 STM32G081:11 STM32H7R3:11 STM32H7S3:11 STM32L083:11 STM32L4R9:11 STM32U345:11 STM32U5A5:11 STM32WBA55:11 STM32F031:10 STM32F071:10 STM32F410:10 STM32F411:10 STM32F427:10 STM32F722:10 STM32F745:10 STM32G414:10 STM32H745:10 STM32L471:10 STM32U599:10 STM32C011:9 STM32F437:9 STM32G441:9 STM32G483:9 STM32G484:9 STM32G4A1:9 STM32H747:9 STM32L443:9 STM32WBA52:9 STM32F102:8 STM32F217:8 STM32F301:8 STM32F407:8 STM32F417:8 STM32F756:8 STM32F769:8 STM32H723:8 STM32H735:8 STM32H753:8 STM32L041:8 STM32L053:8 STM32U083:8 STM32U5F9:8 STM32WBA54:8 STM32WBA65:8 STM32F030:7 STM32F078:7 STM32F098:7 STM32F423:7 STM32F777:7 STM32H730:7 STM32L100:7 STM32L422:7 STM32L462:7 STM32F105:6 STM32F215:6 STM32F733:6 STM32G030:6 STM32H7B0:6 STM32H7R7:6 STM32H7S7:6 STM32L010:6 STM32L475:6 STM32WBA62:6 STM32WLE4:6 STM32WLE5:6 STM32F038:5 STM32F405:5 STM32F732:5 STM32G050:5 STM32H750:5 STM32H755:5 STM32H757:5 STM32L081:5 STM32L082:5 STM32L486:5 STM32L4S5:5 STM32L4S9:5 STM32U5A9:5 STM32U5G9:5 STM32F058:4 STM32F070:4 STM32F107:4 STM32F415:4 STM32F730:4 STM32F779:4 STM32G0B0:4 STM32H733:4 STM32L021:4 STM32U5F7:4 STM32WBA23:4 STM32WBA25:4 STM32WBA50:4 STM32F048:3 STM32F750:3 STM32G070:3 STM32L062:3 STM32L063:3 STM32L4R7:3 STM32L4S7:3 STM32WB15:3 STM32WL55:3 STM32L432:2 STM32U5G7:2 STM32WB35:2 STM32WBA5M:2 STM32WBA63:2 STM32WBA64:2 STM32WL54:2 STM32F768:1 STM32F778:1 STM32L442:1 STM32WB10:1 STM32WB1M:1 STM32WB30:1 STM32WB50:1 STM32WB5M:1 STM32WBA6M:1
<blank>  (1 row; the unclassified family = "STM32" bucket, see §3.3)
```

### 3.7 Illustrative STM32 rows (sample, 6 of 2,411)

| family | subfamily | plasma_series | part_number | identifier_kind | target_config | validation_status |
|---|---|---|---|---|---|---|
| STM32C0 Series | STM32C011 | STM32C0 | STM32C011D6YxTR | cmsis_device_name | tcl/target/stm32c0x.cfg | not_verified |
| STM32C0 Series | STM32C011 | STM32C0 | STM32C011F4Px | ordering_pattern | tcl/target/stm32c0x.cfg | not_verified |
| STM32C0 Series | STM32C011 | STM32C0 | STM32C011F4Ux | ordering_pattern | tcl/target/stm32c0x.cfg | not_verified |
| STM32C0 Series | STM32C011 | STM32C0 | STM32C011F4UxTR | cmsis_device_name | tcl/target/stm32c0x.cfg | not_verified |
| STM32C0 Series | STM32C011 | STM32C0 | STM32C011F6Px | ordering_pattern | tcl/target/stm32c0x.cfg | not_verified |
| STM32C0 Series | STM32C011 | STM32C0 | STM32C011F6Ux | ordering_pattern | tcl/target/stm32c0x.cfg | not_verified |

---

## 4. Boundaries and explicitly-not-made claims

1. **No exact commercial ICPN for STM32.** `manufacturer_part_number` within the STM32 set is 0. The 167
   exact-MPN rows in the whole catalog are all non-STM32. No part number is inferred.
2. **No completeness claim against the STM32 commercial product universe.** `catalog_origin` is observed as
   `openocd-parts-expanded.csv` in sampled rows, and every STM32 row is `mapping_status = mapping_candidate`
   and `validation_status = not_verified`. This is a derived, expanded, candidate and unverified mapping, not a
   validated commercial catalog.
3. **No 1:1 OpenOCD `.cfg` ↔ commercial STM32 series claim.** 2,411 rows collapse to 24 distinct `.cfg` /
   23 series / 22 families; counts differ and the table carries no join proving a bijection.
4. **`ordering_pattern` / `cmsis_device_name` are not exact ICPN.** Their `part_number` cells are
   classification/ordering tokens, some containing wildcard characters (e.g. `x`).
5. **9 STMicroelectronics rows are non-STM32-classified** (e.g. non-`stm32` vendor lines) and are excluded
   from the STM32 tier; they are not enumerated here.
6. **No web research** was consulted; every figure derives from the single source-parse.

---

## 5. Reproducibility

- Single source file: `data/device-catalog/research/openocd-parts-canonical.csv`.
- Single deterministic parse (one open / one `csv.DictReader` pass); all figures taken from that pass.
- Classification rules as defined in §1.
- Verification run (this run): `git diff --check` and `git status --short` performed at report creation;
  results recorded in the mission completion report. No commit was made.

**Not validated / out of scope for this pass:** Z2 / FPGA / real-target programming; validation of any
`mapping_candidate` on hardware; OpenOCD `.cfg` execution; correspondence of any single `.cfg` to a specific
commercial series; and completeness of the STM32 product family relative to any external commercial
datasheet list. None of these were attempted or claimed.
