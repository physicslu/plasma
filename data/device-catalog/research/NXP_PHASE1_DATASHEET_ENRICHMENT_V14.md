# NXP Phase 1 IC Information — NXP datasheet enrichment v14

**Only panel 01 IC Information**, under ADR-0002 already merged in #858. This research PR
changes no Production identities, public IC selector, OpenOCD software qualification,
Programming Profiles, Job/Batch behavior, electrical programming, or HIL.

## 27 source-attested additions

**KL25:** 12 exact commercial part numbers in NXP KL25P80M48SF0 Rev.5 page 2
ordering table (Flash 32/64/128 **KB**, SRAM 4/8/16 **KB**) and page 7 Table 5
(VDD and VDDA each 1.71–3.6 V, with |VDD−VDDA| ≤ 0.1 V). Values are retained
in the source's original KB wording; nothing converts KB to KiB.

**LPC844/LPC845:** 15 exact commercial suffixes are listed in the NXP
LPC84x Product Quality page. The LPC84x datasheet Rev.2.1 page 4
Tables 1–2 resolves the corresponding **eight type-number** forms:
64 KB Flash; LPC844 8 KB SRAM, LPC845 16 KB SRAM; four documented
package groups; VDD 1.8–3.6 V and Tamb −40 to 105 °C (pages 3, 46).
All 15 remain **RESEARCH_ONLY**, not internally admitted or software SUPPORTED.

**Detected discrepancy: 5 JHI33 ordering variants.** The datasheet calls
package **HVQFN33 / 33 terminals**, while the NXP commercial Quality
tab displays **HVQFN32** for those corresponding commercial types.
Record **CONFLICT** for both package and pin-count fields and preserve
both source statements; do **not** silently assume physical pinout
or Socket compatibility. Pin count is total package terminals, not
number of accessible GPIOs. Independently verified package nomenclature
and accurate terminal/electrical mapping require separate review.

**Analog domain:** KL25 VDDA is from the separate Table 5 constraint;
LPC84x Table 11 has **conditional** VDDA minima (ADC/DAC operating modes),
so no single general VDDA row is fabricated. I/O Supply is still UNKNOWN
where the documents do not provide a separately qualified supply domain.

## Data contract

- Full 501 exact ordering-code information is retained and byte-reproducible
  from v13 input plus the source-attested 27-row v14 overlay. `VERIFIED`
  indicates an official manufacturer **field** with an auditable page/table
  and (where necessary) suffix mapping; **it never grants identity
  admission or software support**. `PARTIAL` flags derived base-device
  labels or earlier incomplete source observations; `CONFLICT` is not
  eligible for automatic presentation as verified hardware metadata.
- Official PDF URLs, revision, pages, exact table contents and suffix
  provenance are recorded. **Original PDF bytes and SHA256 were NOT
  acquired or archived**, so the provenance must not claim original
  bytes are SHA-locked. The transcript/ledger is source-locked by Git.
- The 474 unchanged source records are byte-level field-preserved from v13.
- Coverage dimensions and denominator remain **501 observed exact order
  strings (224 admitted identities, 277 unadmitted research candidates)**.
  This is not the world-wide NXP market denominator.

## Phase separation

Existing v9–v12 source review remains archived for Phase 2 Programming;
Phase 3 Compatibility not attempted. Zero software/HIL/public visibility
claims are introduced in this Phase 1 record set.

### Primary official sources

- https://www.nxp.com.cn/docs/en/data-sheet/KL25P80M48SF0.pdf
- https://www.nxp.com/docs/en/data-sheet/LPC84x.pdf
- https://www.nxp.com/products/LPC84X?tab=Package_Quality_Tab

> **v15 supersession — NXP official Fig. 7/42 reviewed:** the five JHI33 package/pin-count `CONFLICT` states here are historical, not current. The physical package consists of 32 perimeter terminals plus center VSS pad #33; datasheet name HVQFN33 and commercial alias HVQFN32 are reconciled in [NXP_PHASE1_LPC84X_PIN_PAD_V15.md](NXP_PHASE1_LPC84X_PIN_PAD_V15.md). No HIL/Socket permission follows.
