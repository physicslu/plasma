# NXP ADR-0002 Phase 1 — LPC822/LPC824 Eight Manufacturer Material Crosswalks v1

## Objective and boundary

Continue existing **OpenOCD-first** discovery, using eight already-identified Wave3 **P0 research leads** (four `LPC822` and four `LPC824`). Build an **original-NXP-document-referenced Phase 1 IC Information crosswalk**, NOT a production catalog addition, a complete OpenOCD software qualification, an installed OpenOCD runtime test, or PS/PL/Site/Socket HIL.

Prior authoritative baselines are left unchanged: historical NXP 501: **P0 27 / P1 38 / P2 436**; discovery Wave2/3/4: **P0 60 / P1 5**. This PR enriches exactly eight **of the existing 60 leads**; it does **not** create eight additional candidates.

## Manufacturer primary sources and evidence strengths

1. [NXP LPC82x product datasheet](https://www.nxp.com/docs/en/data-sheet/LPC82X.pdf), **Rev. 1.5 — 7 February 2023**:
   - **Table 1**, printed p3/82: the **four base ordering strings** and `HVQFN33` / `TSSOP20`.
   - **Table 2**, printed p3/82: `LPC822M101` has **16 KB Flash, 4 KB SRAM**, `LPC824M201` has **32 KB Flash, 8 KB SRAM** in both packages.
   - **Table 3**, printed p9/82: `VDD` supplies the **I/O pad ring, core regulator, and analog peripherals**. `VREFP` is ADC positive reference, not a dedicated analog power rail. `VSS` is contact **33** on `HVQFN33` (exposed pad semantics require exact socket footprint review).
   - **Table 7**, printed p33/82: normal `VDD = 1.8–3.6 V`, and the stated temperature scope is **−40 to +105°C**. Do **not** use absolute maximum **+4.6 V** as working VDD.
2. [NXP official LPC82X Package/Quality — Environmental Information](https://www.nxp.com/products/LPC82X?tab=Package_Quality_Tab): separate **material rows** list **all eight exact suffixed codes** and individual **Active** states, with manufacturer 12NC material numbers.
3. Previously merged NXP Wave3 pinned upstream source: `tcl/target/lpc8xx.cfg → tcl/target/lpc1xxx.cfg → src/flash/nor/lpc2000.c` and symbolic `LPC822_101` / `LPC824_201` driver Part ID case candidates. Pinned OpenOCD **v0.12.0** commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`.

**Original-evidence custody is not solved:** the original official NXP PDF binary and live manufacturer webpage/HTML binary are **not archived/SHA256-locked** by this PR. SHA1 source locks refer to the **PLASMA in-Git source transcription and prior ledgers**, not original NXP file binary bytes. Online document revisions or materials can change.

## Eight source-observed exact material codes (not Production)

| Exact NXP material code | Manufacturer 12NC | Base | Flash | SRAM | Package |
|---|---|---|---:|---:|---|
| `LPC822M101JDH20J` | `935304005118` | `LPC822M101JDH20` | 16 KB | 4 KB | TSSOP20 |
| `LPC822M101JHI33E` | `935304007551` | `LPC822M101JHI33` | 16 KB | 4 KB | HVQFN |
| `LPC822M101JHI33K` | `935304007557` | `LPC822M101JHI33` | 16 KB | 4 KB | HVQFN |
| `LPC822M101JHI33Y` | `935304007518` | `LPC822M101JHI33` | 16 KB | 4 KB | HVQFN |
| `LPC824M201JDH20J` | `935304006118` | `LPC824M201JDH20` | 32 KB | 8 KB | TSSOP20 |
| `LPC824M201JHI33E` | `935304008551` | `LPC824M201JHI33` | 32 KB | 8 KB | HVQFN |
| `LPC824M201JHI33K` | `935304008557` | `LPC824M201JHI33` | 32 KB | 8 KB | HVQFN |
| `LPC824M201JHI33Y` | `935304008518` | `LPC824M201JHI33` | 32 KB | 8 KB | HVQFN |

### Package naming reconciliation — no silent simplification

The NXP **product Quality page says `HVQFN32`** (external/perimeter contacts), but **Rev 1.5 Datasheet Table 1 says `HVQFN33`** (33 total terminals including exposed center VSS). Preserve *both source labels*, source context, and effective contact semantics for any subsequent Socket design. Do not infer that a 32-pin connector footprint and a 33-contact device are identical without verifying pad land pattern and center pad grounding.

### Electrical caution

- **Core and GPIO/analog peripherals share `VDD`**; no independent programmable `VDDIO` or `VDDA` supply is established by the cited evidence.
- **`VREFP` is ADC reference:** datasheet Table 7 lists **2.4 V minimum and VDD maximum**. Do not silently equate an ADC-reference constraint with the IC's 1.8 V minimum core/GPIO operational supply.
- Some digital pins are 5V-tolerant in defined conditions, **not** evidence that 5V can be driven into VDD or all SWD lines in any PPU state.
- Manufacturer datasheet working ranges are **not** socket power rails, OpenOCD programmed voltage, or safe active-SWD pins automatically.

## Software/Phase gates

The listed pinned `lpc2000.c` has `LPC822_101` and `LPC824_201` family-ID cases. It is **not yet proven** that every observed commercial part/revision maps to the ID seen by an installed OpenOCD target; ROM IAP geometry, security/CRP, erase/program/read/verify, installed runtime and PPU SWD electrical/protocol gates require independent qualification.

Thus:
- Existing 65 discovery lead priorities **unchanged**; eight exact material observations receive research-only Phase 1 source crosswalk entries.
- Original `orderable_identity_qualified=false` in prior Wave3 is **not mutated**; these observations strengthen the manufacturer exact-suffix identity evidence but **do not independently archive immutable manufacturer bytes** or establish all packing/material variants' qualification.
- All eight `openocd_programming_qualified=false`, `production_admitted=false`, `physical_hil_verified=false`.
- No changes to Product Catalog, default Selector, API/Job/Batch, OpenOCD binary, PS/PL, PPU/Socket/Site, firmware, Render, or physical hardware.

## CI and reviewer checklist

```bash
python data/device-catalog/research/nxp_phase1_lpc82x_exact_v1.py
python -m unittest discover -s data/device-catalog/research \
  -p 'test_nxp_phase1_lpc82x_exact_v1.py' -v
```

The script replays the previously merged 501+65 ledgers, validates exact eight normalized source strings and NXP 12NCs, validates Table 1/2 memory and Table 3/7 power semantics, preserves HVQFN32/HVQFN33 labels, and fails closed on false Original-PDF/HTML archive or `SUPPORTED` / Production / HIL state claims.

**Draft / no merge without separate explicit owner approval.** After approval, the next step would be additional P0 families, not broad P2 enrichment or a premature direct-to-Production jump.
