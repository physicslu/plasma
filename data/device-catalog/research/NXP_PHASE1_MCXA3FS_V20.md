# NXP Phase 1 v20 — official MCX A3 exact SRAM evidence

NXP original source: [MCX A3 Family Fact Sheet](https://www.nxp.jp/docs/en/fact-sheet/MCXAFS.pdf), PDF **physical page 3**,
table **MCX A3 MCU options**. All **32** exact MCU order codes
in the table have independently documented Flash and SRAM and match
the corresponding already-admitted 32 NXP exact ICPNs. Source rows and
the complete resulting 501-row Phase1 dataset are Git-blob locked.

RAM coverage in the existing **224** NXP Production identities:
**146 VERIFIED / 13 PARTIAL / 65 UNKNOWN**, compared with
114 / 13 / 97 in v18. In the original **501** ICPN combined
Research+Admitted cohort: **161 VERIFIED / 61 PARTIAL / 279 UNKNOWN**.

**Revision metadata discrepancy:** PDF footer reads `MCXA3FS REV 0`
while the NXP product documentation listing says `Rev 1.0, 30 Mar 2026`.
Both are recorded explicitly and no equivalence is fabricated.
Original PDF bytes and a verified SHA256 of the original PDF
were **not durably archived**. Official source and exact page table
transcription remain independently auditable.

No VDD/VDDA/VDDIO, OpenOCD/Erase/Program/Verify,
Production admission, public Catalog/Console, Runtime, PL,
Site/PPU or HIL changes. Phase1 IC Information only.
