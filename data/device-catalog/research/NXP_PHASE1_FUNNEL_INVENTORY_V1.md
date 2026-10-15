# NXP ADR-0002 — Phase 1 Exact ICPN Funnel Inventory v1

**Scope:** NXP only. This is a **bounded, offline-replayable research inventory**, not an NXP-wide MCU population or automatic Production Catalog migration. The source locks and cohort boundaries are fixed as of this change. P0/P1/P2 source-priority counts are intentionally not used as Phase KPIs.

## Executive summary

| Metric (distinct complete ICPN strings) | Replayed count | Qualification |
| --- | ---: | --- |
| Known legacy + reverse-discovered observations/candidates | **566** | Scope only: source-locked historical 501, plus 65 disjoint OpenOCD-first research observations |
| **Phase 1 `S1` — manufacturer identity `IDENTIFIED`** | **240** | **224** preexisting admitted exact identities + **16** directly official material/12NC-observed LPC811/812/822/824 identities. **New 16 remain Research-only, not Production admitted** |
| Phase 1 `S1_complete` — full IC Information fields | **0** | Strict *currently documented* full-field evidence; cannot infer independent VDDIO/VDDA or treat unknown as N/A |
| Phase 1 identity evidence still under review | **326** | **70** prior exact-part HTML partial, **207** prior source-blocked/schema, **49** other reverse-discovered strings still missing an independently reviewed exact manufacturer material crosswalk |
| Phase 2 `S2` software-qualified | **NOT AUDITED** (`null`) | Cannot infer a zero or a supported count from Phase 1 ledgers |
| Phase 3 `S3` physical HIL passed | **NOT AUDITED** (`null`) | Physical configuration-level qualification requires a separate source of truth |

The 566 strings are **not all Phase 1 PASSED** and are **not** a count of all available NXP MCUs. This report deliberately preserves the distinction: a syntactically complete string in research is not necessarily a proven manufacturer commercial order code.

## Audit trail and exact identity decision

1. The v13 501 ledger contains **224 `ADMITTED` existing manufacturer exact identities**, with NXP original source links and provenance retained. Counting these identities in `S1` **does not** imply any current public Catalog eligibility or OpenOCD software qualification.
2. **16 additional exact LPC811/812/822/824 materials** are individually observed at official NXP Package/Quality pages and mapped to actual datasheet bases, packages, Flash/SRAM, normal operating VDD and 12NC. Under revised ADR-0002, original bytes not permanently archived are an **independent source-custody deficit**, not an automatic reason to discard an unambiguous official exact commercial identity. These 16 are **still not admitted to Production**.
3. The **70** v13 `EXACT_PART_HTML_PARTIAL_REVIEW` rows preserve individual page SHA observations, but the frozen field ledger explicitly marks `base_device=UNKNOWN`. They remain Phase 1 identity review backlog **until an official Base/Family relationship and the material identity evidence are reconciled**; no automatic 70 promotions.
4. The other **207** v13 research rows have `NO_EXACT_HTML_SOURCE_BYTES` and schema/source blockers. Official-looking URLs or suffix patterns alone are **not identity proof**.
5. The reverse-discovery 65 ledger is **disjoint** from historical 501. Its **16** enriched materials are counted above, while **49** remain research. This includes **44 P0 / 5 P1 historical priority observations**, neither of which is a Phase progress state. Within the remaining 49, some have official material Active observations but no reviewed exact material/Base identity crosswalk; **1** product-level lifecycle observation must not be upgraded to material-level Active.

## Visible Information Quality Gaps

- **212 / 224** existing admitted records use the full orderable ICPN string as their recorded `base_device` in the normalized v13 ledger. Their original family field exists in upstream admission inputs (MCX / K32L2), but **Base Device normalization needs a separately evidenced, non-heuristic reconciliation**. This does not revoke the prior exact commercial identity admission.
- **224 / 224** old admitted identities have `ram=UNKNOWN`, `working_vdd=UNKNOWN`, `io_supply=UNKNOWN`, `vdda=UNKNOWN` in the v13 Phase 1 ledger. For the entire 501, I/O Supply and VDDA are `UNKNOWN`. Missing fields are not zero.
- The **16** LPC81x/LPC82x exact materials have informative VDD and Flash/SRAM data, but their official sources do not establish independent VDDIO / VDDA rails. **"No separate rail evidenced" is not the same as a demonstrated `NOT_APPLICABLE`.** Therefore they are `S1 IDENTIFIED`, but not claimed to be `S1_complete`.
- **212** admitted legacy records contain an exact official-HTML SHA observation, but the SHA value **does not establish permanent custody of original NXP HTML bytes**. **16** newly identified materials explicitly have `original_{pdf,html}_bytes_archived=false`. Track this custody separately from exact identity acceptance.
- All historical P0/P1 counts, software qualification, physical HIL and current public-selector migration remain outside this Phase 1 report.

## Next execution order — NXP only

1. **Reverse-discovered remaining 49**: prioritize official exact material and family/Base crosswalks by an OpenOCD CFG/Driver family. For already verified source-visible materials, a family-bound batch can move many identities into `S1` without performing Phase 2 erase/program/verify research. Do **not** synthesize order codes from family prefixes or mix material/package forms.
2. **70 previously HTML-observed historical research ICPNs**: resolve exact ordering identity vs Base/Family links from existing official sources; do not mistake missing RAM/VDDA for missing commercial identity.
3. **207 source-blocked historical rows**: bulk official manufacturer listing/export when available; leave `RESEARCH_ONLY` until evidence is obtained.
4. **Field completeness**: run manufacturer datasheet/ordering table crosswalk **by family** rather than per-order-code, with exact variant applicability. Track `S1_complete` independently and preserve unknown VDDIO/VDDA.
5. **Future separate audit**: derive `S2` only from actual Version/Operation-Locked OpenOCD software qualifications, `S3` only from configuration-locked PPU HIL. Do not fill nulls from historical P0/P1/CFG quantities.

## Reproducible evidence and stop gates

The Python verifier uses *Git blob SHA-1* to lock the **four existing PLASMA-transcribed research files** (501 v13, 65 reversed, 8 LPC82x, 8 LPC81x); their blob identifiers are embedded in the verifier. **This is not SHA-256 custody of the NXP manufacturer's original web/PDF bytes.**

```bash
python data/device-catalog/research/nxp_phase1_funnel_audit_v1.py
python -m unittest discover -s data/device-catalog/research -p 'test_nxp_phase1_funnel_audit_v1.py' -v
```

CI must fail if original source bytes mutate, counts or identities overlap, research-only identities are silently admitted, a manufacturer URL is forged, new LPC sources falsely claim original-byte custody/software support/production/HIL, or Phase 2/3 null measurements become fabricated totals.

**No automatic update to Production Identity Store, public Catalog/IC Selector, API, Job/Batch, PPU, FPGA, OpenOCD binary or Phase 3 HIL. A separately approved later PR is needed for any such changes.**
