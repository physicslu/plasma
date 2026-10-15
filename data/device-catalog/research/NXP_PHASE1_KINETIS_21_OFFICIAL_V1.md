# NXP ADR-0002 — Kinetis K40 / K60 / KL46 / KL43 Phase 1 official material evidence (v1)

**Status:** NXP-only research, exact commercial ICPN identity `IDENTIFIED`. The official NXP product/Package-Quality material lists were directly reviewed on **2026-10-15**. This is not an independently archived manufacturer original HTML/PDF source, OpenOCD software `SUPPORTED`, Production admission, public IC Selector eligibility or PLASMA hardware/HIL PASS.

## Cumulative Phase 1 counts, unique complete commercial ICPN strings

| Metric | Previously merged baseline | This proposed incremental research | Delta |
| --- | ---: | ---: | ---: |
| Bounded manufacturer-observed / reverse-candidate source universe | 571 | **576** | +5 (new same-family materials) |
| **Phase 1 `S1 IDENTIFIED`** | **276** | **297** | **+21** |
| `S1_complete` — independently verified mandatory IC Information fields | 0 | **0** | 0 |
| Phase 1 identity-evidence backlog | 295 | **279** | **−16** |
| Unreconciled original OpenOCD reverse leads | 18 | **2** | **−16** |
| Phase 2 exact-ICPN OpenOCD `S2` | Not audited (`null`) | **Not audited** | No certification |
| Phase 3 PPU-Site-Socket-HIL `S3` | Not audited (`null`) | **Not audited** | No certification |

**Snapshot formula:** historical `S1=276` + 16 **exact manufacturer confirmed original CFG-reverse K40/K60/KL46** + 5 **individually confirmed additional NXP KL4x/K60 materials** = `S1=297`. Source universe expands by only 5 from 571 to 576. Backlog remains 70 legacy partial exact HTML/Base unknown + 207 source-blocked legacy + **2** unresolved original reverse leads = **279**.

### Official NXP family batches

| Official manufacturer product page | Direct reverse candidates | Additional official same-family products | Total new S1 | NXP material evidence |
| --- | ---: | ---: | ---: | --- |
| [K40 100 MHz Package/Quality](https://www.nxp.com/products/K40_100?tab=Package_Quality_Tab) | 4 | 0 | 4 | All four named exact materials separately Active, 12NC, package |
| [K60 100 MHz Package/Quality](https://www.nxp.com/products/K60_100?tab=Package_Quality_Tab) | 5 | 1 | 6 | Five reverse materials plus real **`MK60DN512VLL10R`**, 12NC `935323339528` |
| [KL4x Package/Quality](https://www.nxp.com/products/KL4x?tab=Package_Quality_Tab) — KL46 | 7 | 0 | 7 | All seven exact MKL46 128/256 kB material codes independently listed |
| [KL4x Package/Quality](https://www.nxp.com/products/KL4x?tab=Package_Quality_Tab) — KL43 | 0 | 4 | 4 | Four independently listed exact MKL43 128/256 kB material codes, **not inferred to match KL46 OpenOCD part-ID cases** |
| **Total** | **16** | **5** | **21** | |

Vendor-verified unique material/12NC, package and product-level family linkage are in `nxp-21-k40-k60-kl4x-official-materials-phase1-v1.csv`. Manufacturer product `Buy/Parametrics` and Supported Parts lists provide background on Flash/SRAM/core/operating ranges; exact silicon revision, separate I/O/analog rails and package-specific electrical requirements are **not** individually requalified as complete. All recorded `working_vdd` values are **normal operating values**, not Absolute Maximum Ratings; that does **not** by itself prove the full VDDIO/VDDA schema.

**No inferred order codes:** `MK60DN512VMC10` and `MK60DN512VMC10R` are distinct official materials with **different manufacturer 12NCs**, as are `MK60DN512VLL10` and `MK60DN512VLL10R`. No suffix is synthesized; the meaning of `R` is not a Phase 1 programming qualification. The KL43 branch is entered by the broad NXP **KL4x manufacturer product/family** relationship, **not** by treating the `kl46.cfg` technical route as qualified KL43 support.

## Original source custody and Source Replay caveat

NXP's original online HTML and datasheet PDF bytes have **not** been archived as immutable original vendor sources; original HTML/PDF SHA-256 are intentionally not claimed. The Git blob SHA-1 embedded in the deterministic verifier locks only PLASMA's extracted/transcribed observation CSV. Each row retains the authoritative NXP URL, 12NC, review date, material scope and matching product/parameter page. This difference is important; a correct official exact-ICPN identity is not a claim that independent original-site bytes have been permanently retained.

## Remaining two exact-ordering ambiguities from original CFG reverse wave

- `LPC1114FBD48/333J`: original visible ordering-display form still needs official material/code normalization; do not create a guessed suffix or `IDENTIFIED` record.
- `LPC2148FBD64`: original product-level display is insufficient to resolve exact `,118 / ,151 / ,157` manufacturer material and corresponding lifecycle. Exact material-level evidence needed; **Product Active** does not imply every material is Active.

The historical 277 source-partial/blocked identities are still in Phase 1 Research and not counted in `S1`. The 212 legacy Base Device normalization issues and unknown I/O/analog rail states also remain.

## Evidence and CI

```bash
python data/device-catalog/research/nxp_phase1_official_lpc_25_v1.py
python data/device-catalog/research/nxp_phase1_kinetis_21_official_v1.py
python -m unittest discover -s data/device-catalog/research -p 'test_nxp_phase1_kinetis_21_official_v1.py' -v
```

The tests explicitly reject fabricated/doubled commercial ICPNs, 12NC mismatch, base/package mismatch, incorrect RAM/Flash, unauthorized source archiving claims, erroneous Phase 1 `INFORMATION_COMPLETE`, Phase 2 `SUPPORTED`, Production or HIL promotion, and unfounded KL43-as-CFG software support.

**This PR changes research data, an auditable offline verifier, its tests and the NXP CI only; it does not modify Production Catalog, public IC Selector, Python application/API, OpenOCD runtime, PS/PL, PPU or physical HIL. No merge without separate owner approval.**
