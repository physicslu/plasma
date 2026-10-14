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

The official Microchip **[SAM D21/DA1 Family Data Sheet, DS40001882H](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU32/ProductDocuments/DataSheets/SAM-D21-DA1-Family-Data-Sheet-DS40001882H.pdf)**, **§8.2.1 Power Supplies**, explicitly lists both **VDDIO = 1.62–3.63 V** and **VDDANA = 1.62–3.63 V**, with VDDIN/VDDIO/VDDANA required to have the same applied voltage. The PLASMA UI field `io_supply` maps to the named VDDIO supply; the UI field `vdda` maps to the **manufacturer name VDDANA**, *not* to the internally regulated **VDDCORE = 1.2 V**. Both fields are `PARTIAL` family datasheet facts until exact commercial variant applicability and original document bytes are independently reviewed.

`base_device` remains `UNKNOWN`, not derived by truncating manufacturer ordering suffixes.

**Reproducibility limitation / release block:** The committed information dataset still records `raw_capture_retained=false` and `raw_capture_sha256=null` for both manufacturer sources; no reviewed immutable response digest has been bound to its field assertions. This PR adds a **bounded, read-only original source-byte capture and hash-replay job**, which retains its results as a separate GitHub Actions artifact, but does **not** automatically upgrade exact-ICPN fields or authorize admission. A successful raw HTML capture does *not* prove a structured Catalog Parts table, and an official PDF raw hash alone does not prove a given page/section applies to the exact orderable variant. This gap remains explicit until a separately reviewed source-to-field replay and exact identity admission decision. The `research_review_date=2026-10-14` is an evidence review date, not the manufacturer's document last-change timestamp.

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
| flash, ram, vdd, io_supply, vdda, core_architecture, core_model (each) | 0 | 2 | 0 | 0 |
| base_device | 0 | 0 | 2 | 0 |

Each row is evaluated against **2 observed exact ordering codes**; these are *not* 2 Production-admitted rows. No total percentage is extrapolated to the larger Microchip population.

## Automated Phase 1 guard

```bash
python -m unittest discover -s data/device-catalog/research \
  -p 'test_microchip_phase1_information_v1.py' -v

python data/device-catalog/research/microchip_phase1_information_v1.py \
  --report /tmp/microchip-phase1-coverage.json

python -m unittest discover -s data/device-catalog/research \
  -p 'test_microchip_phase1_source_capture_v1.py' -v

# From a network-enabled runner; only official allowlisted Microchip URLs
python data/device-catalog/research/microchip_phase1_source_capture_v1.py \
  --capture /tmp/microchip-original-phase1-sources

# Replay original archive and its SHA-256 independently (no manufacturer write)
python data/device-catalog/research/microchip_phase1_source_capture_v1.py \
  --verify /tmp/microchip-original-phase1-sources
```

The validator fails closed for wrong/extra fields, duplicate exact ICPN, missing original units, untraceable manufacturer source, family-level facts incorrectly elevated to `VERIFIED`, false original-byte hashes, unknown becoming 0, and any inserted Phase 2/3 or Production permissions.

The generated report explicitly separates observed exact Research identities, internal admitted counts and each field's VERIFIED/PARTIAL/UNKNOWN/CONFLICT counts. This is a **data contract and evidence-quality regression**, not a claim that original manufacturer's source bytes were successfully replayed.

The source-capture job is deliberately **best effort**: inaccessible or HTML-only manufacturer pages remain explicit `SOURCE_NOT_AVAILABLE` or `SOURCE_RESPONSE_INVALID` blockers, not fabricated archived evidence. Captured source bytes and SHA-256 checks are replayable for **integrity only**. The job never claims a field has passed original-byte semantic verification.

## Remaining Phase 1 blockers and next work

1. Review the official original-byte capture artifact; where product-site Catalog Parts are dynamic or inaccessible, obtain a retained official ordering-code table or Microchip MCP original raw exact part record, then bind source bytes + SHA-256 to the exact ordering rows.
2. Confirm the manufacturer's true `base_device` relation, exact variant applicability for product-family Flash, RAM, VDD, **VDDIO** and **VDDANA**, and explicitly preserve the datasheet supply-pin naming.
3. Independently verify source PDF section and revision `DS40001882H §8.2.1` against the archived bytes; source byte integrity is distinct from field-semantic correctness.
4. Expand only a bounded source-replayable Phase 1 ICPN cohort, quantify source/capture/unknown/conflict denominators, and request a separate owner-reviewed internal-admission gate.

**Explicitly excluded:** silicon Flash-controller semantics, Programming Guide, OpenOCD operations/software qualification, public Catalog/API/IC Selector filtering, PPU, Socket, Adapter, HIL, firmware/FPGA and Job/Batch execution. The previous OpenOCD-first Research material stays intact for later phases.
