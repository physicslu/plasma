# Microchip ADR-0002 Phase 1 — IC Information pilot (Research only)

**Status:** Phase 1 bounded evidence pilot; **not** internally admitted, Production published, software-qualified, or physically verified.

**Authority:** [ADR-0002 Phase 1](../../../docs/adr/0002-openocd-software-qualified-catalog-visibility.md). Phase 2 Programming and Phase 3 PLASMA Compatibility are expressly deferred. Existing [OpenOCD-first P0/P1/P2](MICROCHIP_OPENOCD_CORE_FIRST_V1.md) may help choose which manufacturer identities are worth examining, but neither Target/Flash Driver investigation nor software `SUPPORTED` status is a Phase 1 deliverable.

## Cohort and source

This intentionally small pilot uses two **exact** Microchip ordering-code rows visible in the manufacturer's [ATSAMD21G18 product page](https://www.microchip.com/en-us/product/ATSAMD21G18), *Catalog Parts* section:

| Exact ICPN | Manufacturer Catalog Parts package | Pins | Exact catalog row temperature |
|---|---|---:|---|
| `ATSAMD21G18A-MU` | VQFN | 48 | -40°C to +85°C |
| `ATSAMD21G18A-MF` | VQFN | 48 | -40°C to +125°C |

The same Microchip product page reports **family-level parametric data** for SAMD21G18: Flash 256 KB, SRAM 32 KB, VDD 1.62–3.63 V, CPU Cortex-M0+. Since these parametrics are shown for the base product **rather than explicitly scoped to each exact ordering code**, the fields are `PARTIAL` pending exact-device applicability review. Original published `KB` units are preserved; no implicit KB→KiB or MB conversion is asserted.

`base_device`, `io_supply` and `vdda` remain `UNKNOWN`, not 0 and not inferred from name suffixes or other families.

**Reproducibility limitation / release block:** The official manufacturer product-page URL and each exact line/parametric locator are recorded, but original HTTP response bytes and their SHA-256 have **not** been captured and preserved. The dataset explicitly records `raw_capture_retained=false` and `raw_capture_sha256=null`. It therefore must **not** be promoted to internal admission on this pilot alone; a later Phase 1 evidence capture/replay or reviewed authoritative ordering/datasheet is still required. The `research_review_date=2026-10-14` is an evidence review date, not a claim that original bytes were retrieved or that the manufacturer page was last revised that day.

The data deliberately does **not** represent all the historical **24,051 Microchip Research candidate ICPNs**, nor the earlier 3,717 DFP device-support names. Neither number is a manufacturer-wide exact-commercial coverage denominator.

## Field-level evidence states and boundaries

- `VERIFIED`: official manufacturer Catalog Parts row names the exact ordering code and explicitly supports the reported value.
- `PARTIAL`: official manufacturer product-family parametric; exact order-code applicability has not independently been proved.
- `UNKNOWN`: missing adequate evidence. Store `null`, never inferred 0 or a parsed package/core/value.
- `CONFLICT`: reserve status for disagreements; do not resolve by silent overwrite or precedence. Contradictory records need independent source review before admission.

Each reported field retains source ID, evidence scope, source locator and original units when relevant. A distinct source manifest retains URL, document identity, review date, original-byte hash **if available**, and data-integrity limits. The dataset's `internal_identity_state=SOURCE_LINKED_EXACT_PART_OBSERVED` is **not** `internal_admission_state=ADMITTED`.

### Initial Phase 1 coverage (two exact Research rows)

| Field | VERIFIED | PARTIAL | UNKNOWN | CONFLICT |
|---|---:|---:|---:|---:|
| manufacturer, icpn, package, pin_count, temperature (each) | 2 | 0 | 0 | 0 |
| flash, ram, vdd, core_architecture, core_model (each) | 0 | 2 | 0 | 0 |
| base_device, io_supply, vdda (each) | 0 | 0 | 2 | 0 |

Each row is evaluated against **2 observed exact ordering codes**; these are *not* 2 Production-admitted rows. No total percentage is extrapolated to the larger Microchip population.

## Automated Phase 1 guard

```bash
python -m unittest discover -s data/device-catalog/research \
  -p 'test_microchip_phase1_information_v1.py' -v

python data/device-catalog/research/microchip_phase1_information_v1.py \
  --report /tmp/microchip-phase1-coverage.json
```

The validator fails closed for wrong/extra fields, duplicate exact ICPN, missing original units, untraceable manufacturer source, family-level facts incorrectly elevated to `VERIFIED`, false original-byte hashes, unknown becoming 0, and any inserted Phase 2/3 or Production permissions.

The generated report explicitly separates observed exact Research identities, internal admitted counts and each field's VERIFIED/PARTIAL/UNKNOWN/CONFLICT counts. This is a **data contract and evidence-quality regression**, not a claim that original manufacturer's source bytes were successfully replayed.

## Remaining Phase 1 blockers and next work

1. Preserve original official page/catalog response bytes with verifiable SHA-256 or obtain a reviewed manufacturer ordering-code table/datasheet; bind exact ordering variants to their authoritative source revision.
2. Confirm the manufacturer's true `base_device` relationship and per-exact-ICPN applicability for family-level Flash, RAM, VDD and Cortex-M0+ facts.
3. Find device/package-specific official evidence for `io_supply` and `vdda` or leave them `UNKNOWN`.
4. Extend only a bounded, source-replayable Phase 1 exact-ICPN cohort, report full field-gap and conflict denominators, then submit a separate, owner-reviewed internal-admission decision.

**Explicitly excluded:** silicon Flash-controller semantics, Programming Guide, OpenOCD operations/software qualification, public Catalog/API/IC Selector filtering, PPU, Socket, Adapter, HIL, firmware/FPGA and Job/Batch execution. The previous OpenOCD-first Research material stays intact for later phases.
