# NXP ADR-0002 Phase 1 v25 — K32L2B 12 exact ICPNs: operating VDD PARTIAL

**Owner-authorized Phase 1 IC Information follow-on from v24.** The project-wide ADR-0002 Phase 2 Programming remains active, but this bounded research stream only fills IC Information gaps. **No Production/Selector, OpenOCD software qualification, Programming Profile, PPU, PL, Site, Socket, HIL or deploy.** Baseline 501 source records (224 already admitted identity + 277 Research-only) stay unchanged.

## Direct source review and critical confidence boundary

1. NXP's [AN12648 K32L2B Headset with NXH3670](https://www.nxp.com/docs/en/application-note/AN12648.pdf), **Rev 0, January 2020, §3.1.1 Host controller, physical PDF page 4 of 9**, explicitly documents **K32L2B operating voltage 1.71–3.6 V**. This is a K32L2B family / application-note description, **not** each order-code's own datasheet operating table.
2. NXP official [K32-L2 product Documentation — K32L2B3x Supported Parts](https://www.nxp.com/products/K32-L2) explicitly lists the 12 pre-existing exact commercial ordering codes (B11/B21/B31 × VFM0A/VFT0A/VLH0A/VMP0A), under **K32L2B3x Rev 3, October 2020**. That original datasheet is **Account Required**, and its complete original bytes/electrical tables **were not accessed**.
3. Already admitted v24 NXP exact ICPN `/part/...` source links, 64/128/256 KiB-class existing Flash fields and existing exact identity are independently cross-checked. NXP [K32L2B31VLH0A product-page search record](https://www.nxp.com/part/K32L2B31VLH0A) also independently displays 1.71–3.6 V for that exact part, but the **v25 12-row decision intentionally does not extrapolate this one exact indexed page to the other eleven**.

**Decision:** Upgrade only `working_vdd` from `UNKNOWN` → `PARTIAL` in these **12** already-admitted K32L2B ICPNs, with `working_vdd="1.71 to 3.6"` V and explicit family-only scope, fixed `AN12648` revision/page, exact NXP supported-parts listing, immutable project-side source transcription Git blob and `NOT_ARCHIVED` original vendor PDF status.

**NOT qualified:** independent VDDIO rail; analog VDDA; per-pin threshold / maximum IO ratings; power-on sequence; guaranteed individual silicon ordering-code VDD; Flash programming; PPU supply / SWD electrical; physical HIL. `io_supply` and `vdda` remain `UNKNOWN`, `ram` remains `PARTIAL` for these 12. Do not misinterpret AN12648's description of functional Flash operations as a Phase 2 OpenOCD software capability.

## 224 admitted exact-ICPN Phase 1 coverage before → after

| IC Information field | v24 VERIFIED / PARTIAL / UNKNOWN | v25 VERIFIED / PARTIAL / UNKNOWN |
| --- | --- | --- |
| RAM | 199 / 25 / 0 | **199 / 25 / 0** |
| Working VDD | 135 / 27 / 62 | **135 / 39 / 50** |
| VDDA | 135 / 0 / 89 | **135 / 0 / 89** |
| I/O Supply | 119 / 16 / 89 | **119 / 16 / 89** |

The larger **501-row research+admitted source scope** becomes Working VDD: 150 VERIFIED / 81 PARTIAL / 270 UNKNOWN, with all other Phase 1 field evidence untouched. There are **12 fewer UNKNOWN VDD**, but **zero additional VERIFIED**, and **zero new exact identities admitted**.

## Deterministic source assets and independent regression

- `nxp-12-k32l2b-working-vdd-partial-source-v25.csv`: 12 exact manufacturer identity crosswalks, official AN12648 link/revision/page, official Supported Parts link, observed voltage, old flash cross-check and explicit inaccessible datasheet/byte-custody states.
- `nxp-phase1-k32l2b-vdd-source-lock-v25.json`: original Git blob SHA of v24 501-row input and frozen 12 source rows; note that **these SHA lock only the PLASMA evidence transcription**, **not** the original PDF.
- `nxp-501-phase1-k32l2b-vdd-partial-v25.csv`: full, deterministic 501-row ledger. Exactly three inherited fields change for the 12 rows: `working_vdd`, `working_vdd_unit`, `working_vdd_state`. New v25 provenance columns are blank for everyone else.
- `nxp-phase1-k32l2b-vdd-partial-coverage-v25.json`: separated admitted versus all-501 counts, source and safety semantics.
- Generator and negative tests verify byte-for-byte reproducibility from source-locked v24, 12 exact commercial identities and old Flash fields, no false `VERIFIED`, original manufacturer PDF hash or unexpected I/O/VDDA/software/HIL/admission promotion.

```bash
python data/device-catalog/research/nxp_phase1_k32l2b_vdd_v25.py
python -m unittest discover -s data/device-catalog/research \
  -p 'test_nxp_phase1_k32l2b_vdd_v25.py' -v
```

**Remaining gap:** The original K32L2B3x datasheet (account required) and associated precise electrical requirements must be obtained through an authorized NXP login or other permitted official acquisition path before an exact-`VERIFIED` voltage or VDDA/I/O rail claim. NXP official AN12648's family voltage is useful as an **incomplete** Phase 1 observation, not electrical signoff for PLASMA hardware.
