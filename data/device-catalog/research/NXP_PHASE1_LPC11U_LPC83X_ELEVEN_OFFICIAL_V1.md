# NXP ADR-0002 Phase 1 — LPC11U / LPC83x 11 official commercial materials v1

**Scope:** NXP only, OpenOCD CFG-first reverse research lead → NXP exact-material/12NC and Datasheet base-device crosswalk → Phase 1 `IDENTIFIED`. No change to Production identity, user-facing Catalog/IC Selector, OpenOCD `SUPPORTED`, PPU/Site/Socket HIL or runtime.

## Reviewed exact-material cohort

| Official NXP family / datasheet | Full material ICPNs | Flash / SRAM | Nominal working VDD | Package scope |
| --- | ---: | --- | --- | --- |
| LPC11U24 — LPC11U2X Rev 2.3 (2014-03-27) | 1 | 32 kB Flash; **6 kB main SRAM + 2 kB USB SRAM** | **1.8–3.6V** | Commercial HVQFN32; datasheet HVQFN33 terminal count (including exposed pad) |
| LPC11U67 — LPC11U6X Rev 1.5 (2020-08-12) | 3 | 128 kB Flash / 20 kB SRAM | **2.4–3.6V** | LQFP48/64/100 |
| LPC11U68 — LPC11U6X Rev 1.5 (2020-08-12) | 5 | 256 kB Flash / 36 kB SRAM | **2.4–3.6V** | LQFP48/64 |
| LPC832 — LPC83X Rev 1.2 (2018-04-04) | 1 | 16 kB Flash / 4 kB SRAM | **1.8–3.6V** | TSSOP20 |
| LPC834 — LPC83X Rev 1.2 (2018-04-04) | 1 | 32 kB Flash / 4 kB SRAM | **1.8–3.6V** | Commercial HVQFN32; datasheet HVQFN33 including exposed pad |
| **Total** | **11** | | | |

**Sources and exact evidence authority:**

- [NXP LPC11U00 Package/Quality](https://www.nxp.com/products/LPC11U00?tab=Package_Quality_Tab): confirms **9 exact materials and unique 12NCs**, including the LPC11U24FHI33/301Y physical commercial suffix (935297186518), LPC11U67JBD100E (935304421551), and LPC11U68JBD64Y (935302501518).
- [NXP LPC81X/LPC83X Package/Quality](https://www.nxp.com/products/LPC81X_LPC83X?tab=Package_Quality_Tab): confirms two more individual **Active** LPC832M101FDH20FP (935309057129), LPC834M101FHI33Y (935309056518).
- [LPC11U2X.pdf](https://www.nxp.com/docs/en/data-sheet/LPC11U2X.pdf), Rev 2.3, **printed page 3, Tables 1 and 2**: confirms LPC11U24FHI33/301 base type, package and **6 kB main + 2 kB USB SRAM**. **Do not conflate** this with an undivided 8 kB contiguous SRAM block.
- [LPC11U6X.pdf](https://www.nxp.com/docs/en/data-sheet/LPC11U6X.pdf), Rev 1.5, **printed page 4, Tables 1 and 2**: confirms LPC11U67/JBD48,64,100 and LPC11U68/JBD48,64 bases and 128/256 kB Flash; 20/36 kB SRAM. **Working VDD: 2.4–3.6 V** (not 1.8 V).
- [LPC83X.pdf](https://www.nxp.com/docs/en/data-sheet/LPC83X.pdf), Rev 1.2, **printed page 3, Tables 1 and 2**: LPC832 16 kB / 4 kB and LPC834 32 kB / 4 kB; commercial **HVQFN32** and package-terminal **HVQFN33** are different presentations, not contradictory exact ordering identity.

**Evidence quality:** original manufacturer HTML and original PDF binary bytes **NOT archived**, and no original manufacturer source SHA-256 custody asserted. Official URL, material 12NC, Datasheet document revision, ordering locator and observed date **2026-10-15** are documented; the PLASMA-transcribed source CSV is separately protected by a Git blob hash. No individual exact silicon ID/revision, software `SUPPORTED`, Production admission, or hardware HIL qualified. Independent VDDIO / VDDA applicability remains **unverified** for purposes of strict `INFORMATION_COMPLETE`.

## Phase 1 funnel delta — unique Exact ICPNs only

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Fixed historical source universe | 566 | **566** | 0 |
| **Phase 1 S1 `IDENTIFIED`** | 240 | **251** | **+11** |
| Phase 1 `INFORMATION_COMPLETE` | 0 | **0** | 0 |
| Phase 1 identity review backlog | 326 | **315** | −11 |
| Legacy partial HTML + unknown Base | 70 | 70 | 0 |
| Legacy source-blocked/schema | 207 | 207 | 0 |
| Reverse CFG candidates awaiting material crosswalk | 49 | **38** | −11 |
| Phase 2 software-qualified S2 | not audited | **not audited** | n/a |
| Phase 3 HIL-qualified S3 | not audited | **not audited** | n/a |

**Cohort summary:** 251 = 224 historical internal admitted exact identities + 16 previously official material-crosswalked LPC81x/LPC82x identities + **11 newly crosswalked NXP materials**. New 27 are **Research-only**, not Production-admitted. The historical P0/P1 labels are not Phase counts.

## Reproducible test commands

```bash
python data/device-catalog/research/nxp_phase1_funnel_audit_v1.py
python data/device-catalog/research/nxp_phase1_lpc11u_lpc83x_11_v1.py
python -m unittest discover -s data/device-catalog/research -p 'test_nxp_phase1_lpc11u_lpc83x_11_v1.py' -v
```

Tests must reject fabricated material suffixes, modified 12NC, family/base mismatch, false 1.8 V minimum on LPC11U6x, unverified source PDF/HTML byte-custody claims, arbitrary software/Production/HIL promotion, and altered Git blob source. The baseline **240** snapshot is intentionally immutable and the new **251** snapshot is an incremental v1 layer; no historical replay result is rewritten.

**Next NXP research:** process the remaining 38 OpenOCD-reverse candidates based on manufacturer exact material evidence, one family batch at a time. Historic 277 Research rows require independent source/base normalization; there is no authorization in this PR to move them into Production or the public IC Selector.
