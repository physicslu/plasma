# NXP ADR-0002 Phase 1 — 25 official LPC material/12NC identities (v1)

**Scope:** NXP only. Follow the approved **OpenOCD CFG → manufacturer product family → exact NXP commercial material** discovery workflow. This report **does not** qualify OpenOCD programming, Production identities, the public IC Selector or PPU HIL.

## What changed

| Metric, distinct full commercial ICPNs | Merged previous | This Draft PR | Delta |
| --- | ---: | ---: | ---: |
| Bounded research universe | 566 | **571** | **+5** new official family material variants |
| **Phase 1 `S1 IDENTIFIED`** | 251 | **276** | **+25** |
| `S1_complete`: all necessary IC Information fields verified | 0 | **0** | 0 |
| Identity evidence review backlog | 315 | **295** | **−20** original reverse leads moved into S1; +5 new sources are directly identified |
| Reverse discoveries still lacking exact NXP material crosswalk | 38 | **18** | −20 |
| Phase 2 OpenOCD `S2` / Phase 3 HIL `S3` | Not audited | Not audited | No qualification |

**New 25:** LPC1758 (4), LPC1768 (3), LPC1769 (3), LPC1778 (2), LPC1788 (2), LPC4088 (2), LPC4078 (1), LPC4357 LBGA256 (2), LPC4357 LQFP208 (2), LPC1549 (2) and LPC2378 (2).

All 25 have **explicit NXP official Product/Package & Quality material name, 12-digit manufacturer 12NC, observed lifecycle, product grouping, official product URL and package**. The first 20 exist in the historical 65-row OpenOCD reverse ledger. The following **five additional real manufacturer material variants were discovered by expanding the official family lists** rather than restricting the process to old 38 candidates:

- `LPC1758FBD80/P1K`, 12NC `935430326557`
- `LPC1758FBD80Y`, 12NC `935288607518`
- `LPC1768FBD100Y`, 12NC `935288608518`
- `LPC1769FBD100K`, 12NC `935290522557`
- `LPC1769FBD100/P1K`, 12NC `935430318557`

## NXP manufacturer sources and evidence boundary

All parts are individually listed on their official **Package/Quality → Environmental Information** tables with unique 12NC. The official product breadcrumb supplies an LPC family/model clue; **the manufacturer's actual Datasheet ordering table and per-field IC Information are not re-certified by this PR**, and are still subject to future `S1_complete` validation.

| Product / NXP official source | Exact records in scope |
| --- | ---: |
| [LPC1758FBD80](https://www.nxp.com/products/LPC1758FBD80?tab=Package_Quality_Tab) | 4 |
| [LPC1768FBD100](https://www.nxp.com/products/LPC1768FBD100?tab=Package_Quality_Tab) | 3 |
| [LPC1769FBD100](https://www.nxp.com/products/LPC1769FBD100?tab=Package_Quality_Tab) | 3 |
| [LPC1778FBD208](https://www.nxp.com/products/LPC1778FBD208?tab=Package_Quality_Tab) | 2 |
| [LPC1788FBD208](https://www.nxp.com/products/LPC1788FBD208?tab=Package_Quality_Tab) | 2 |
| [LPC4088FBD208](https://www.nxp.com/products/LPC4088FBD208?tab=Package_Quality_Tab) | 2 |
| [LPC4078FBD208](https://www.nxp.com/products/LPC4078FBD208?tab=Package_Quality_Tab) | 1 |
| [LPC4357FET256](https://www.nxp.com/products/LPC4357FET256?tab=Package_Quality_Tab) | 2 |
| [LPC4357JBD208](https://www.nxp.com/products/LPC4357JBD208?tab=Package_Quality_Tab) | 2 |
| [LPC1549JBD100](https://www.nxp.com/products/LPC1549JBD100?tab=Package_Quality_Tab) | 2 |
| [LPC2378FBD144](https://www.nxp.com/products/processors-and-microcontrollers/arm-microcontrollers/general-purpose-mcus/lpc2000-arm7/arm7-with-512kb-flash-58-kb-sram-ethernet-usb-2-0-device-can-and-10-bit-adc:LPC2378FBD144?tab=Package_Quality_Tab) | 2 |

**Important canonicalization nuance:** for some legacy NXP materials, the UI displays the commercial part `LPC1788FBD208` and separately a **material declaration** `LPC1788FBD208,551`, 12NC `935291861551`. These representations are kept in **different columns**, not silently concatenated. Other commercial suffixes such as `K`, `Y` and `/P1K` are retained exactly as listed. Each exact ICPN counted once; separate 12NC checked unique.

**Original-source custody is NOT established:** The NXP original HTML bytes were not archived/SHA256-hashed. This PR locks **PLASMA's human-transcribed manufacturer observations** by their Git blob SHA; original page URL, observation date and exact material row locator are preserved. `SOURCE_BYTES_NOT_ARCHIVED` remains a separate evidence-quality gap. A confident manufacturer material observation is not automatically a proven silicon revision or software qualification.

## Why LPC2148 and LPC1114 remain uncounted

After the 20 reverse-lead matches, **18 historical reverse candidates remain**, including 16 K40/K60/KL46, one `LPC1114FBD48/333J` with raw-display/ordering-normalization ambiguity, and one `LPC2148FBD64` where the NXP Package/Quality page distinguishes specific `,118 / ,151 / ,157` material suffixes with **different lifecycle states** (the `,118` material is No Longer Manufactured while `,151 / ,157` are Active). A bare product header's Active badge is **not exact material lifecycle proof**. These are quarantined for a separately reviewed exact-material admission decision rather than inventing their original orderable identity.

## Engineering controls

Source CSV: `nxp-25-lpc-exact-material-12nc-phase1-v1.csv`. Verifier: `nxp_phase1_official_lpc_25_v1.py`. Synthetic negative tests: `test_nxp_phase1_official_lpc_25_v1.py`. Approved prior **251 Phase 1 baseline is replayed unchanged**; cumulative audit derives **571 universe / 276 identified / 295 backlog / 18 pending reverse**. Source-custody, software support and physical safety flags all stay false or unknown.

```bash
python data/device-catalog/research/nxp_phase1_funnel_audit_v1.py
python data/device-catalog/research/nxp_phase1_lpc11u_lpc83x_11_v1.py
python data/device-catalog/research/nxp_phase1_official_lpc_25_v1.py
python -m unittest discover -s data/device-catalog/research -p 'test_nxp_phase1_official_lpc_25_v1.py' -v
```

**No alteration to manufacturer Research originals, Production admission, public Catalog/IC Selector, Job/Batch, OpenOCD runtime/flash driver, FPGA, Site, Socket or HIL. Owner approval required for merge.**
