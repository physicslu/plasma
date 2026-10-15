# NXP OpenOCD CFG-first reverse discovery — Wave 4 (2026-10-15)

## Executive verdict

A bounded owner-authorized continuation of ADR-0002 *Phase-1 research prioritization* from **the pinned OpenOCD v0.12.0 CFG → shared Tcl target → `lpc2000` Flash Driver → original NXP product/Material status**. Do not confuse source availability and exact-ordering research priority with confirmed Flash programming operations, software support, installed PPU compatibility, or HIL.

- **20 newly observed strings** (none occur in the previously sealed 501 + Wave2 27 + Wave3 18): **18 P0 research discovery candidates**, **2 P1 target/driver-ID-gap candidates**.
- One separate **No Longer Manufactured** material (**LPC810M021FN8FP**) excluded despite an OpenOCD driver Part ID.
- **Three** official NXP source pages checked, **five** pinned upstream source Git blobs; page-byte SHA/DOM capture remains **not available**, and no manufacturer-wide denominator exists.

### Source-first exact candidate matrix

| Family | New material/part strings | P0 / P1 | OpenOCD pinned chain / evidence |
|---|---|---|---|
| LPC811 | `LPC811M001JDH16FP`, `LPC811M001JDH16J` | 2 P0 | `lpc8xx.cfg → lpc1xxx.cfg → lpc2000.c`; `LPC811_001` case |
| LPC812 | `LPC812M101JD20J`, `LPC812M101JDH16FP`, `LPC812M101JDH16J`, `LPC812M101JDH20FP`, `LPC812M101JDH20J`, `LPC812M101JTB16X` | 6 P0 | Same; `LPC812_101` and four ID variants in source |
| LPC11U24 | `LPC11U24FHI33/301Y` | 1 P0 | `lpc11xx.cfg → lpc1xxx.cfg → lpc2000.c`; `LPC11U24_301` & `_401` |
| LPC11U67 | `LPC11U67JBD100E`, `LPC11U67JBD48E`, `LPC11U67JBD64E` | 3 P0 | Same; `LPC11U67_1`/`_2` |
| LPC11U68 | `LPC11U68JBD48E`, `LPC11U68JBD48K`, `LPC11U68JBD64E`, `LPC11U68JBD64K`, `LPC11U68JBD64Y` | 5 P0 | Same; `LPC11U68_1`/`_2` |
| LPC1769 | `LPC1769FBD100` | 1 P0 *product-level only* | `lpc17xx.cfg → lpc1xxx.cfg → lpc2000.c`; `LPC1769` case. **Only product header Active, not exact material row verified** |
| LPC832 | `LPC832M101FDH20FP` | 1 P1 | `lpc8xx.cfg` generic target/Flash bank exists; explicit `LPC832` Part ID **not found** in pinned driver |
| LPC834 | `LPC834M101FHI33Y` | 1 P1 | Same missing explicit `LPC834` driver ID case |
| **Total** | **20** | **18 P0 / 2 P1** | No `SUPPORTED` or Production admission |

Official manufacturer references (current public-page observations, not raw-byte replay):

1. [NXP LPC81X/LPC83X Package/Quality](https://www.nxp.com/products/LPC81X_LPC83X?tab=Package_Quality_Tab): exact material rows show LPC811/812/832/834 Active; `LPC810M021FN8FP` **No Longer Manufactured**, excluded.
2. [NXP LPC11U00 Package/Quality](https://www.nxp.com/products/LPC11U00?tab=Package_Quality_Tab): per-material LPC11U24/67/68 Active. Beware this same page includes **some other** LPC11U material revisions with mixed Active/No Longer Manufactured; never infer all variants Active.
3. [NXP LPC1769FBD100](https://www.nxp.com/products/LPC1769FBD100): product-level **Active**. Material-level exact orderable code and packaging status have **not** been replayed and therefore remain a separate gap.

### OpenOCD original source and audit boundary

All Tcl/Flash source assertions refer only to **upstream v0.12.0 commit** `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`:
- [Target Tcl folder](https://github.com/openocd-org/openocd/tree/9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c/tcl/target);
- [`lpc2000.c` Part-ID implementation](https://github.com/openocd-org/openocd/blob/9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c/src/flash/nor/lpc2000.c).

Source identities are Git-blob pinned for `lpc8xx.cfg`, `lpc11xx.cfg`, `lpc17xx.cfg`, `lpc1xxx.cfg`, and `lpc2000.c`. An existing independently pinned source-lock inventory (merged PR #885) provides the comparison authority. **CI validates Git blob identities and deterministic ledger rules offline; it does not download/replay the current NXP HTML pages or execute the OpenOCD binary.**

**Engineering stop gates:**
- `lpc2000.c` device Part ID cases express *silicon families*, **not a one-to-one proof for each physical ordering/packing code**, ROM revision, clock/geometry and programming outcome. No erase/write/read/verify or Flash security behavior is qualified.
- Generic `lpc8xx.cfg` with `lpc2000 auto` does **not** qualify LPC832/LPC834 when the pinned driver lacks explicit IDs: keep P1.
- Material `LPC810M021FN8FP` is **No Longer Manufactured** even though OpenOCD recognizes LPC810 silicon: exclude from Active-based discovery, do not declare all LPC810 incompatible.
- Product-level `LPC1769FBD100` Active does **not** equal independent per-material Active and must remain explicitly weaker evidence until reviewed.
- Phase 1 review would require independently retained official manufacturer HTML/source rows and normalized commercial ordering identities. No NXP global Active or total support-count inference.
- Phase 2 qualification and execution/hardware gates remain deferred/independent under ADR-0002.

### Deterministic validation

```bash
python data/device-catalog/research/nxp_validate_source_first_wave4_v1.py
python data/device-catalog/research/test_nxp_source_first_wave4_v1.py -v
```

The tests reject Source Git blob drift, new/unreviewed part addition, historical overlap with previous 501/27/18 records, P1→P0 without Part ID, false material-vs-product lifecycle, fabricated manufacturer HTML custody, NLM→Active, non-NXP URLs, and `SUPPORTED`/Production/HIL promotion.

**Impact:** Research only. No Production Catalog, IC Selector, Program Profile, Job/Batch, runtime binary, Render, PPU, FPGA/PL or hardware operation changes. Draft PR requires independent owner approval before merging.
