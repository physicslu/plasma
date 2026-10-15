# NXP Phase-1 OpenOCD-first — Vendor Exact Part Reverse Discovery v2

**Scope:** Bounded evidence-gathering round approved by project owner: start from pinned OpenOCD Target Config, walk into pinned target helper and Flash Driver, then look up NXP official **Active** ordering strings. This is NOT a NXP-global portfolio census, nor a Phase-2 Programming Profile / `SUPPORTED` decision.

**Baseline:** OpenOCD upstream `v0.12.0`, source commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`; older NXP v10 research **501** exact records (P0 27/P1 38/P2 436) and PR #885's bounded reverse index. That previous review found no new exact P0 **inside 501**. This round specifically searches **outside 501** and must not modify the historic ledger.

## First wave: 27 additional manufacturer Active observations outside the original 501

| Target Config → Flash Driver | Official NXP observed parts | Qty | Status |
| --- | --- | ---: | --- |
| `k40.cfg → kx.cfg → kinetis.c` | `MK40DN512VLK10`, `MK40DN512VLL10`, `MK40DN512VLQ10`, `MK40DN512VMD10` | 4 | Active on NXP K40_100 Package/Quality |
| `k60.cfg → kx.cfg → kinetis.c` | `MK60DN512VLL10`, `MK60DN512VLQ10`, `MK60DN512VMD10`, `MK60DN512VMC10`, `MK60DN512VMC10R` | 5 | Active on NXP K60_100 Package/Quality |
| `kl46.cfg → klx.cfg → kinetis.c` | `MKL46Z128VLH4`, `MKL46Z128VLL4`, `MKL46Z128VMC4`, `MKL46Z256VLH4`, `MKL46Z256VLL4`, `MKL46Z256VMC4`, `MKL46Z256VMP4` | 7 | Active on NXP KL4x Package/Quality |
| `lpc11xx.cfg → lpc1xxx.cfg → lpc2000.c` | `LPC1114FBD48/333J` | 1 | Active on NXP LPC1100 Package/Quality; `LPC1114_333` explicit ID exists in driver |
| `lpc17xx.cfg → lpc1xxx.cfg → lpc2000.c` | `LPC1758FBD80`, `LPC1758FBD80K`, `LPC1768FBD100`, `LPC1768FBD100K` | 4 | Active on respective NXP Package/Quality pages; explicit `LPC1758`/`LPC1768` IDs in driver |
| `lpc40xx.cfg → lpc1xxx.cfg → lpc2000.c` | `LPC4088FBD208`, `LPC4088FBD208K` | 2 | Active on LPC4088 official page; explicit `LPC4088` ID in driver |
| `lpc4357.cfg → lpc4350.cfg → lpc2000.c` | `LPC4357FET256`, `LPC4357FET256K`, `LPC4357JBD208E`, `LPC4357JBD208K` | 4 | Active on two NXP LPC4357 Package/Quality pages; dual 512 KiB bank CFG |
| **Total** | **27 distinct strings, none in original 501** | **27** | **Source-backed P0 DISCOVERY CANDIDATES ONLY** |

The NXP Package/Quality pages contain some bare part/package labels and separate material-declaration / packing suffixes (e.g. `,551`). The rows here preserve **exactly the displayed part strings** rather than manufacturing an unverified canonical ordering suffix. A later admission pass must unambiguously crosswalk to official orderable identifier, packaging, silicon revision, and exact NXP lifecycle. Do **not** interpret the 27 candidate strings as approved Production ICPNs.

### Authoritative live NXP source entrypoints (9 bounded pages)

- [K40 100 MHz Package/Quality](https://www.nxp.com/products/K40_100?tab=Package_Quality_Tab)
- [K60 100 MHz Package/Quality](https://www.nxp.com/products/K60_100?tab=Package_Quality_Tab)
- [Kinetis KL4x Package/Quality](https://www.nxp.com/products/KL4x?tab=Package_Quality_Tab)
- [LPC1100 Package/Quality](https://www.nxp.com/products/LPC1100?tab=Package_Quality_Tab)
- [LPC1758FBD80 Package/Quality](https://www.nxp.com/products/LPC1758FBD80?tab=Package_Quality_Tab)
- [LPC1768FBD100 Package/Quality](https://www.nxp.com/products/LPC1768FBD100?tab=Package_Quality_Tab)
- [LPC4088FBD208 Package/Quality](https://www.nxp.com/products/LPC4088FBD208?tab=Package_Quality_Tab)
- [LPC4357FET256 Package/Quality](https://www.nxp.com/products/LPC4357FET256?tab=Package_Quality_Tab)
- [LPC4357JBD208 Package/Quality](https://www.nxp.com/products/LPC4357JBD208?tab=Package_Quality_Tab)

**Provenance limitation:** Current research review observed current official HTML-backed Active rows, but original rendered web page/DOM *bytes and SHA-256 have NOT been durably acquired*. This study expressly marks `manufacturer_page_bytes_archived=false`, and does **not** claim Phase-1 per-field `VERIFIED`, complete current lifecycle capture, or immutable original-page replay. Phase-1 identity acceptance needs a properly captured source snapshot and ordering-code reconciliation.

### OpenOCD pinned source evidence

- [Upstream OpenOCD Target at exact commit](https://github.com/openocd-org/openocd/tree/9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c/tcl/target).
- [`kinetis.c` source at exact commit](https://github.com/openocd-org/openocd/blob/9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c/src/flash/nor/kinetis.c).
- [`lpc2000.c` source at exact commit](https://github.com/openocd-org/openocd/blob/9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c/src/flash/nor/lpc2000.c).

NXP K40/K60/KL46 Target scripts set the appropriate Kinetis chip name and include a shared Target which instantiates a `kinetis` flash bank. LPC11xx/17xx/40xx use `lpc2000 auto` with the family-specific series and clock/working-area settings. LPC4357's dedicated config instantiates two `lpc2000 lpc4300` flash banks. `lpc2000.c` source contains explicit LPC1114_333, LPC1758, LPC1768 and LPC4088 IDs, and documents testing LPC4357.

**Safety/operation blockers:** Kinetis Flash Configuration Field `0x400–0x40F`, security/recovery, dynamic SDID/FCFG geometry; LPC ROM IAP part-ID matching, reset clock, checksum modifications and unknown Part ID failure path; LPC4357 dual Flash banks. Driver source symbols and TCL configuration do not independently qualify erase/program/read/verify per exact ordering variant, transport, or installed PPU binary. No programming/security bit operations are executed in this research.

## Acceptance boundary

The 27 new strings are a **bounded discovery queue**: source-backed Target/Driver and NXP Active observation justify prioritizing next **Phase 1 identity/source capture**, but do not unilaterally raise the existing official P0 count from 27 to 54. No transfer from discovery queue to `openocd_software_support=SUPPORTED` is allowed. After Phase 1 source replay/ordering identity is admitted, the exact Flash/ROM operation qualification belongs to separately authorized ADR-0002 Phase 2.

The 27 are a *first wave from 9 pages*, **not an exhaustive answer** to all of OpenOCD’s 48 NXP candidate configs, all NXP Active order codes or the NXP portfolio. We explicitly do not infer anything about i.MX RT from older i.MX application-processor configs, or from RT600 DSP debug definitions; unrelated LPC13xx examples may be End-of-Life (see NXP official product pages) and should not be silently marked Active.

## Deterministic CI

```bash
python data/device-catalog/research/nxp_validate_source_first_active_v2.py
python data/device-catalog/research/test_nxp_source_first_active_v2.py -v
```

These validate 27 candidates are disjoint from the original 501, preserve pinned OpenOCD version/13 source Git blobs, 9 exact official URLs, candidate-only permissions and the absence of unsupported promotion. Offline tests cannot re-prove manufacturer website statements without archived original HTML bytes; capturing and replaying these bytes is the separate Phase-1 evidence-completion gate.

**No Production Catalog, IC Selector, Job/Batch, OpenOCD runtime, PPU, Render or Hardware HIL changes. Merge remains owner-approved only.**
