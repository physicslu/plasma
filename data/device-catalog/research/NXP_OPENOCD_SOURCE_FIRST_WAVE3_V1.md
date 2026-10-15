# NXP OpenOCD CFG-first reverse discovery — Wave 3 (Phase 1 research)

**Decision:** Following explicit owner approval of PR #887, continue source-first discovery outside the previous 501 review and 27-wave2 manufacturer observations, from the pinned OpenOCD Target CFG → shared Tcl → Flash Driver → public NXP original product page. This wave is **research-only** (no Phase 2 Programming qualification, no Product Catalog admission).

## Result: 18 new official-page observations from 7 product pages

| Family | Exact NXP part strings observed as Active (unless noted) | P0/P1 | OpenOCD v0.12.0 route |
| --- | --- | --- | --- |
| LPC822 | `LPC822M101JHI33E`, `LPC822M101JHI33K`, `LPC822M101JHI33Y`, `LPC822M101JDH20J` | 4 P0 | `lpc8xx.cfg → lpc1xxx.cfg → lpc2000.c`; `LPC822_101` silicon IDs in driver |
| LPC824 | `LPC824M201JHI33E`, `LPC824M201JHI33K`, `LPC824M201JHI33Y`, `LPC824M201JDH20J` | 4 P0 | same; `LPC824_201` silicon IDs |
| LPC1778 | `LPC1778FBD208`, `LPC1778FBD208K` | 2 P0 | `lpc17xx.cfg → lpc1xxx.cfg → lpc2000.c`; `LPC1778` Part ID |
| LPC1788 | `LPC1788FBD208`, `LPC1788FBD208K` | 2 P0 | same; `LPC1788` Part ID |
| LPC4078 | `LPC4078FBD208` | 1 P0 | `lpc40xx.cfg → lpc1xxx.cfg → lpc2000.c`; `LPC4078` Part ID |
| LPC2378 | `LPC2378FBD144`, `LPC2378FBD144K` | 2 P0 technical discovery | `lpc2378.cfg → lpc2xxx.cfg → lpc2000.c`; ARM7 JTAG route, manufacturer **NRND** |
| LPC2148 | `LPC2148FBD64` (material variants **,151 and ,157 Active; ,118 No Longer Manufactured**) | 1 P1 ordering/lifecycle ambiguity | `lpc2148.cfg → lpc2xxx.cfg → lpc2000.c`; ARM7 JTAG route, manufacturer NRND |
| LPC1549 | `LPC1549JBD100E`, `LPC1549JBD100K` | 2 P1 | `lpc2000.c` recognizes a `lpc1500` Flash Driver variant, but **no dedicated `lpc1549.cfg` Target Config** in pinned upstream `tcl/target/` |

**Totals:** 18 newly observed identifier strings, **15 source-backed P0 investigation leads**, **3 bounded P1 leads**, **0 software SUPPORTED**, **0 Production admission**. P0 here is an **investigation priority**, not an approved updated v10 source-locked priority count (27), not per-exact-silicon demonstrated operation and not a JTAG/PPU hardware qualification.

### Original NXP Official Package/Quality (bounded, not NXP global population)

- [LPC82X](https://www.nxp.com/products/LPC82X?tab=Package_Quality_Tab) — direct environmental table shows four LPC822 and four LPC824 exact material/order strings as Active.
- [LPC1778FBD208](https://www.nxp.com/products/LPC1778FBD208?tab=Package_Quality_Tab) — both package material strings Active.
- [LPC1788FBD208](https://www.nxp.com/products/LPC1788FBD208?tab=Package_Quality_Tab) — both material strings Active.
- [LPC4078FBD208](https://www.nxp.com/products/LPC4078FBD208?tab=Package_Quality_Tab) — one listed Active material.
- [LPC2378FBD144](https://www.nxp.com/products/processors-and-microcontrollers/arm-microcontrollers/general-purpose-mcus/lpc2000-arm7/arm7-with-512kb-flash-58-kb-sram-ethernet-usb-2-0-device-can-and-10-bit-adc:LPC2378FBD144?tab=Package_Quality_Tab) — both Active, **not recommended for new designs**.
- [LPC2148FBD64](https://www.nxp.com/products/processors-and-microcontrollers/arm-microcontrollers/general-purpose-mcus/lpc2000-arm7/single-chip-16-bit-32-bit-microcontrollers-up-to-512-kb-flash-with-isp-iap-usb-2-0-full-speed-device-10-bit-adc-and-dac:LPC2148FBD64?tab=Package_Quality_Tab) — page-header Active does **not** mean all material declarations Active: `,118` is No Longer Manufactured while `,151` and `,157` are Active. It remains P1 pending ordering-code disambiguation.
- [LPC1549JBD100](https://www.nxp.com/products/LPC1549JBD100?tab=Package_Quality_Tab) — E/K materials Active, but Driver exists without identified dedicated upstream CFG; P1 only.

**Manufacturer source custody gap:** Original rendered HTML bytes and per-SKU manufacturer SHA-256 are **not captured**. Current public evidence is not equivalent to a byte-immutable, independently replayable NXP Phase-1 exact part admission. `manufacturer_original_html_archived=false`, all entries keep `production_admitted=false`.

### Pinned OpenOCD evidence and transport boundary

OpenOCD upstream `v0.12.0` at commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`. The [Tcl Target folder](https://github.com/openocd-org/openocd/tree/9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c/tcl/target) and [`src/flash/nor/lpc2000.c`](https://github.com/openocd-org/openocd/blob/9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c/src/flash/nor/lpc2000.c) are linked by the eight Git-blob hashes pinned in `nxp-openocd-source-first-wave3-v1.json`; the offline checker cross-compares to previously committed PR #885 upstream index.

LPC822/824, LPC1778/1788 and LPC4078 have driver Part ID switch cases; **they still require exact NXP order code ↔ actual silicon Part ID and revision**. LPC2378 and LPC2148 use **Arm7TDMI JTAG**, not FPGA SWD; no JTAG-capable PLASMA Site/PPU execution or programming validity is claimed. NRND is an economic/stock prioritization concern, not synonymous with No Longer Manufactured.

No `LPC1549` target config with Flash Bank route is established, despite `lpc2000.c` mentioning `LPC1500`. This must remain P1; do not synthesize a Target file from generic C code.

### Validation / stop rule

```bash
python data/device-catalog/research/nxp_validate_source_first_wave3_v1.py
python data/device-catalog/research/test_nxp_source_first_wave3_v1.py -v
```

Replays the fixed exact 18 strings, compares them to original NXP 501 and PR #887 27 (no duplication), rechecks OpenOCD pinned version/source/driver blobs, fixes 15 P0 and 3 P1 roles and refuses unapproved source hashes, fake HTML archive, omitted JTAG/NRND note, P1→P0, mixed-lifecycle promotion, or software/HIL/Production promotion.

**This wave is complete as a bounded research input only; not a NXP-wide source enumeration or a certified exact-programmable list.** Keep v10's historical P0=27 unchanged until a separate approval of exact-source identity expansion. No Product Catalog, Programming, OpenOCD runtime, PPU/PS/PL, Render, or Job/Batch code changed.
