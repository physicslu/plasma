# NXP ADR-0002 — Phase 1 LPC811/LPC812 Eight Exact Manufacturer Materials v1

## Scope

Continue the already approved OpenOCD-first ADR-0002 source-first research on **8 pre-existing Wave4 P0 discovery leads**. No new candidate classification or software/public/Production admission is authorized. Historical NXP 501: P0 27, P1 38, P2 436; 65 external research leads: P0 60, P1 5. These **8 are part of the existing 60**, not added on top.

## Original NXP reference crosswalk

- [NXP LPC81XM Product Datasheet](https://www.nxp.com/docs/en/data-sheet/LPC81XM.pdf), **Rev 4.7 — 19 March 2021**, **Table 1 and Table 2 (printed p3 of 78)**: six distinct base order codes, package types, Flash/SRAM.
- [NXP LPC81X/LPC83X official Package/Quality material listing](https://www.nxp.com/products/LPC81X_LPC83X?tab=Package_Quality_Tab), **Environmental Information**: eight exact suffixed material/order part strings, each individually displayed Active and with a distinct manufacturer 12NC.
- LPC81XM **Table 9 Static Characteristics (printed p33/78)**: VDD (core and external rail) **1.8–3.6 V**; **−40 to +105°C** ambient for these non-DIP packages. Do NOT substitute **+4.6 V** from the Absolute Maximum Ratings (Table 7, p31/78).
- LPC81XM: single supply; SWD and JTAG boundary scan modes supported. The comparator analog functions do not substantiate a separately programmable VDDA pin; neither independent VDDIO nor independent VDDA should be invented.
- Previous NXP Wave4: OpenOCD upstream **v0.12.0** at `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c` has `tcl/target/lpc8xx.cfg -> tcl/target/lpc1xxx.cfg -> src/flash/nor/lpc2000.c`, with LPC811_001 and LPC812_101 variant driver Part ID leads. These are **source-first research leads**, not eight exact silicon probe/Flash-operability qualification results.

## Eight exact source observations

| Manufacturer material code | 12NC | Base device | Package | Flash | SRAM |
| --- | --- | --- | --- | ---: | ---: |
| `LPC811M001JDH16FP` | `935302397129` | LPC811M001JDH16 | TSSOP16 | 8 KB | 2 KB |
| `LPC811M001JDH16J` | `935302397118` | LPC811M001JDH16 | TSSOP16 | 8 KB | 2 KB |
| `LPC812M101JD20J` | `935302399118` | LPC812M101JD20 | SO20 | 16 KB | 4 KB |
| `LPC812M101JDH16FP` | `935302398129` | LPC812M101JDH16 | TSSOP16 | 16 KB | 4 KB |
| `LPC812M101JDH16J` | `935302398118` | LPC812M101JDH16 | TSSOP16 | 16 KB | 4 KB |
| `LPC812M101JDH20FP` | `935302401129` | LPC812M101JDH20 | TSSOP20 | 16 KB | 4 KB |
| `LPC812M101JDH20J` | `935302401118` | LPC812M101JDH20 | TSSOP20 | 16 KB | 4 KB |
| `LPC812M101JTB16X` | `935301584115` | LPC812M101JTB16 | XSON16 | 16 KB | 4 KB |

Note: `LPC812M101JD20J` has an SO20 package and is **not** a TSSOP20 or TSSOP16, and XSON16 does **not** imply interchangeable footprints even with another 16-terminal package.

## Research qualification boundaries

1. **Do not conflate vendor observation and immutable evidence custody.** Original NXP PDF bytes and manufacturer HTML bytes were consulted online, **not locally archived or byte-SHA256-locked**. PLASMA Git blob hashes lock only repository-side transcriptions and the already pinned source-ledger material.
2. Material-level `Active` is from NXP's official visible page, not a guarantee of stock or support across silicon/ROM revisions.
3. Manufacturer base-order Datasheet tables plus material 12NC do **not** independently prove the exact physical ROM/Flash silicon Part ID, reset and ISP/IAP constraints, Clock/CRP, erase/program/verify, PPU installed OpenOCD runtime, Socket/Site power or SWD readiness.
4. All eight remain `programming_qualified=false`, `production_admitted=false`, `physical_hil_verified=false`, and `exact_silicon_revision_verified=false`.
5. This PR affects only `data/device-catalog/research/` and its isolated `.github/workflows/` check. No Production Catalog/Selector/API/Job/Batch/PS/PL/HIL/Render changes.

## Validation

```bash
python data/device-catalog/research/nxp_phase1_lpc81x_exact_v1.py
python -m unittest discover -s data/device-catalog/research -p 'test_nxp_phase1_lpc81x_exact_v1.py' -v
```

The verifier replays the original 501 and 65 discovery rows from repository-source SHA1 Git blobs, then checks exact eight 12NC/base/package/memory/source/supply/temperature fields. Negative tests reject false archive, support, wrong VDD/Memory/package and promotion. **Keep the PR Draft; merging requires separate explicit owner approval.**
