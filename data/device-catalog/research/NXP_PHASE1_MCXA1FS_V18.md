# NXP ADR-0002 Phase 1 v18 — MCX A1 exact official RAM evidence

**Status:** Research-only data enrichment, no default Catalog, Runtime or Production admission changes.
Upstream manufacturer: [NXP MCXA1FS Rev 0, 30 March 2026](https://www.nxp.com/docs/en/fact-sheet/MCXA1FS.pdf).
Official **MCX A1 MCU options** tables occupy PDF physical pages **2–4**.

## Evidence review

76 explicit commercial ordering codes were manually transcribed from
the official PDF MCU-options tables with their per-row Flash and SRAM.
An exact string join (plus Flash capacity equality check) to our original
501 NXP observations yields **72 admitted identities** and **4 existing
Research-only identities**. All 72 existing admitted Flash values match the
source; their previously UNKNOWN RAM fields can therefore become VERIFIED.

The other four codes are **already present in the 277 original
Research-only cohort**, not newly discovered externally:
`MCXA144VLH`, `MCXA145VLH`, `MCXA146VLH`,
`MCXA155VLH`. Although present in the official MCXA1FS table,
they are kept as Research-only with existing Phase 1 metadata untouched
until separate internal identity admission review is authorized.
No automatic SKU admission occurs.

## Coverage

Of the **224 existing admitted NXP ICPNs**, RAM changes from
**42 VERIFIED / 13 PARTIAL / 169 UNKNOWN** (v17) to
**114 VERIFIED / 13 PARTIAL / 97 UNKNOWN** (v18).
Across all original 501 exact observations RAM becomes
**129 VERIFIED / 61 PARTIAL / 311 UNKNOWN**.

The source only establishes original official Flash and SRAM values by
exact order code. VDD, VDDA, VDDIO, Programming and Compatibility
are **not** derived from it.

## Evidence limitations

This official PDF was reviewed by page, but original PDF bytes are
**not persistently stored or SHA256-qualified**. The review is an
exact official-source transcription pinned by Git object hash, *not*
a claim that original binary files are permanently preserved.
No XLS or dynamic NXP Buy/Parametrics export was acquired.
The earlier v17 224-ICPN parametric-source audit remains historical
and its 13-indexed + 26-fact-sheet observed-row counts must not be
mistaken for the total v18 source-backed SRAM population.

Tests replay original v17 501 identities, source v18 exact 76, verify
72 Flash equality gates, 4 unchanged Research identities, no voltage
field mutation and exhaustive 501-row output/coverage equality.
