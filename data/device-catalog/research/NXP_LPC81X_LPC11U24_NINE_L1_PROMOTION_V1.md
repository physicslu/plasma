# NXP LPC811 / LPC812 / LPC11U24 — nine exact L1 programming candidates

**Proposed, independent PR. Base `main`: `6b451b73f670010537c5cdd8e40ab04494923172`.**

## ADR-0002 scope / Product contract

Nine **official manufacturer exact material codes**, no prefix-manufactured suffixes: LPC811 (2), LPC812 (6), LPC11U24 (1). Eight LPC81X sources originate in the sealed `nxp-8-lpc81x-phase1-official-material-v1.csv` research record; one LPC11U2X source from `nxp-11-lpc11u-lpc83x-phase1-official-material-v1.csv`. Each Original Manufacturer Material code is paired with its official 12NC and a Datasheet Ordering Base; Family/Package/Flash are source-specific.

**Canonical projection, subject to CI:** NXP exact **232→241**, L0 **212**, L1 **20→29**, L2 **0**, L3 **0**. All nine are `PROGRAMMING_CANDIDATE`, `job_selectable=false`, `execution_authorized=false`. Retain ST 65 L2, Microchip L0 122. Global intended exclusive L0=437 / L1=4,490 / L2=65 / L3=0; exact total 4,992.

## Source authority

- LPC811/LPC812 manufacturer: [NXP LPC81X/LPC83X Package & Quality](https://www.nxp.com/products/LPC81X_LPC83X?tab=Package_Quality_Tab), [LPC81xM Datasheet Rev 4.7](https://www.nxp.com/docs/en/data-sheet/LPC81XM.pdf) Tables 1 and 2. Eight independent Material/12NC lines; known NLM LPC810 material and unstated LPC812 packages are excluded.
- LPC11U24 manufacturer: [NXP LPC11U00 Package & Quality](https://www.nxp.com/products/LPC11U00?tab=Package_Quality_Tab), [LPC11U2x Datasheet Rev 2.3](https://www.nxp.com/docs/en/data-sheet/LPC11U2X.pdf) Tables 1 and 2. **Exact** `LPC11U24FHI33/301Y` with official 12NC `935297186518`, Ordering Base `LPC11U24FHI33/301`, 32 KiB Flash, 33-terminal HVQFN datasheet vs marketed HVQFN32 housing. The slash and `Y` commercial suffix must survive API/Selector exactly. NXP also provides an independent chemical-content declaration for this exact material.
- OpenOCD v0.12.0, upstream `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`:
  - LPC811/812: `tcl/target/lpc8xx.cfg` (blob `4c54a2a6670d6186297306112deee8d25e2627e4`) → `tcl/target/lpc1xxx.cfg` (blob `70d26d2673900b06c6d5eef8e55b4542103e9e42`) → `src/flash/nor/lpc2000.c` (blob `f12eef7e4ce68fc8830773f6c57da57dfb87d6b8`), driver Part-ID cases `LPC811_001`, `LPC812_101` and `_1/_2/_3`.
  - LPC11U24: `tcl/target/lpc11xx.cfg` (blob `d288e2a32b08b5e9ad26b7c86fb7035e8e08b1b6`) → same helper and driver, explicit `LPC11U24_301` and `LPC11U24_401` cases.
- Repository research ledgers and upstream target locks are Git blob pinned; production CSVs are Git blob + SHA-256 pinned in Manifest.

## Explicit limitations / safety contract

Original manufacturer webpage HTML and datasheet PDF bytes were **not archived** in the historical Research collection; do not claim original-byte replay or that 2026-10-16 live pages have been archived. Browser-observed official source pages can corroborate identity but are not substituted for evidence original-byte custody.

The specified CFG, Include chain and explicit part-ID branches make L1 plausible; they **do not establish installed OpenOCD runtime, exact silicon revision, physical SWD, Flash sector/page/erase/program/verify behavior, security unlock, IAP workspace validity or L2 `SUPPORTED`**. Any missing/conflicting such qualification evidence remains a L1→L2 blocker. ProgrammingQualificationRegistry is sole Catalog Level authority; CatalogPromotionFramework only observes.

Legacy Research `P0/P1` priority is **not** Product maturity. The sealed older research rows retain their original `production_admitted=false` historical observation, even while the new canonical Production publication correctly marks admitted identities. Runtime, Job and HIL are independent.

No deployment, hardware IO, or programming job. **No merge without owner Gate 2 approval.**
