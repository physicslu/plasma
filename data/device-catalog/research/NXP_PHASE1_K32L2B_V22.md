# NXP ADR-0002 Phase 1 v22 — 12 K32L2B bounded official group-RAM observations

Only 01 IC Information. The **12 remaining** RAM UNKNOWN
within the **224 NXP admitted exact identity** cohort belong to the
K32L2B11 / B21 / B31 groups. The original official NXP Datasheet
`K32L2B3x` (Rev 3) is inaccessible as a downloadable primary PDF
in this research environment, and **is not claimed reviewed**.

Two independently published original NXP sources provide matching
group-level RAM evidence:

- [AN12779 Rev 0 July 2020, section 1.1 Table 1](https://www.nxp.com/docs/en/application-note/AN12779.pdf)
  specifies `K32L2B11Vxx0A` 64 KB Flash / 32 KB RAM,
  `K32L2B21Vxx0A` 128 KB / 32 KB,
  and `K32L2B31Vxx0A` 256 KB / 32 KB.
- [K32 L2 original Fact Sheet orderable device table](https://www.nxp.com/docs/en/fact-sheet/K32-L2-FS.pdf)
  independently reports the same three grouped order-code patterns and
  32 KB SRAM.
- NXP [K32-L2 Supported Parts](https://www.nxp.com/products/K32-L2)
  lists the 12 exact current commercial strings, which are also the
  previously admitted internal identities: `VFM0A`, `VFT0A`,
  `VLH0A`, `VMP0A` for each of B11/B21/B31.

The generator compares exact full ICPN, bounded suffix, grouped model
pattern, and previously admitted Flash capacity; otherwise it fails.
**All 12 RAM values are `PARTIAL`, never `VERIFIED`**, because the
same original table does not show all twelve exact strings and RAM
values together. Original K32L2B3x Datasheet and exact
Buy/Parametrics export remain needed to close the final evidence gate.

## Resulting admitted cohort RAM evidence

- 199 `VERIFIED` (unchanged; direct official exact ordering tables)
- 25 `PARTIAL` (13 indexed Parametrics rows + 12 group-cross-referenced)
- 0 `UNKNOWN`

**This is not 224 independently verified RAM values.** It means
all 224 now have a nonempty research field, but 25 still lack
the highest source confidence.

The complete original 501 exact research/admitted observations are
preserved and deterministic. No changes to Production Manifest,
public Console/API, OpenOCD software qualification, PPU/Site/Socket,
programming procedures, hardware/HIL, Working VDD, VDDA, or I/O Supply.
Manufacturer original PDF binaries have not been durably archived and
no original binary SHA256 is asserted.
