# Microchip frozen 2,563 Phase 1 — SAM L10/L11 exact PDF field enrichment

## Scope and authoritative facts

This bounded addendum follows [ADR-0002](../../../docs/adr/0002-openocd-software-qualified-catalog-visibility.md),
the already merged 2,563-member exact-ICPN/CFG
[freeze](MICROCHIP_5CFG_2563_PHASE1_ST_FIELDS_V1.md), and ST's per-field
`VERIFIED / PARTIAL / UNKNOWN / CONFLICT` evidence structure.

**Do not widen the 2,563 exact ICPN frozen cohort or recalculate P0/P1/P2.**

In the `tcl/target/atsaml1x.cfg` group there are 126 original
Microchip MCP exact commercial order codes and twelve original Base Devices.
The existing source-locked
`microchip_phase1_p1_ordering_crosswalk_v1.py` independently replays both
the publisher MCP source and official revisioned PDF:
[Microchip SAM L10/L11 DS60001513G](https://ww1.microchip.com/downloads/en/DeviceDoc/SAM-L10L11-Family-Data-Sheet-DS60001513G.pdf).

- Official PDF original-byte SHA-256:
  `ee9c04451141173b787374388ddf9b607a5a569415ae85d9b5715237fd1cbb9e`.
- Printed **p.14 Table 1-1** contains family memory, pin and core evidence.
- Printed **p.16 Ordering Information** defines package code, grade,
  factory options and permitted ordered variants.
- **122** existing exact vendor MCP part numbers match the official ordering
  grammar and explicit variant restrictions.
- **4** actual vendor MCP part numbers have a special `VAO` suffix not
  defined by the PDF's ordinary grammar and must **remain pending**.

## Exact applicability and field evidence decision

This change *does not* treat arbitrary family Chart values as exact-SKU proof.

For each of the 122 ordinary commercial ICPNs, qualification requires
**two original manufacturer evidence layers** and an applicability check:

1. Microchip's own original MCP `partNumber` and `basePartNumber`,
   original response SHA-256 and Phase 1 `IDENTIFIED` for the exact SKU.
2. The publisher PDF's original SHA/revision, p.14 **same Base Device**
   feature table, and p.16 explicit **same SKU suffix** packaging/temperature
   rule; no contradictions and a valid supported variant. The original PDF
   **does not enumerate full commercial SKU strings**; the manufacturer MCP
   exact material record is the separate proof that each order code exists.
3. The existing manufacturer Chart supplies a separate Base-only PARTIAL
   value; any prior CONFLICT/VERIFIED/UNKNOWN instead of approved PARTIAL
   stops the promotion. No external guessing or generic CPU inference.

Given the cross-source exact-SKU applicability, the new
`microchip_phase1_p1_exact_pdf_field_enrichment_v1.py` marks **six**
strictly scoped fields `VERIFIED` on the **122** ordinary ICPNs:

| New exact-order evidence | Source rule |
|---|---|
| Package | Printed p.16 ordering code A/M/U/Y, checked against family package restrictions |
| Pin Count | Printed p.14 Table 1-1 D=24 / E=32 and same exact MCP Base |
| Main Flash | Printed p.14 Base Device Main Flash **KB**, not Data Flash |
| SRAM | Printed p.14 Base Device RAM **KB**, not generic family maximum |
| Temperature grade | Printed p.16 material grade U/F/Z, preserve minimum and maximum °C |
| Core Model | Printed p.14 and p.16 Arm Cortex-M23 device family |

**No new Phase 2 software capability is claimed.** A program memory
size field is *not* a programming algorithm/Flash Driver qualification.

These fields have separate source location, original
MCP/PDF source hashes, value/unit, publisher authority, revision,
`VERIFIED` state and descriptive applicability. Original source bytes
are replayed by upstream CI; this derived script does **not** independently
download the PDF or original manufacturer MCP data.

## Actual expected per-field post-overlay states

| Field (per exact ICPN) | VERIFIED | PARTIAL | UNKNOWN |
|---|---:|---:|---:|
| Manufacturer, exact ICPN, Base Device | 2,563 | 0 | 0 |
| Package, Pin Count, Main Flash, SRAM, Temperature, Core Model | **122** | **2,374** | 67 |
| Working VDD | 0 | 2,496 | 67 |
| I/O Supply, VDDA, Core Architecture | 0 | 0 | 2,563 |

- New exact-source field promotions: **6 × 122 = 732**.
- The **4 VAO** records retain original Chart PARTIAL fields and
  explicit source-review exceptions.
- Frozen exact ICPN/CFG/Base SHA:
  `0c37ad68c1db0a4fb50ff5a1d229faaca0ee6eac44cfb9d9b7de4e8a931daf2a`.
- `S1 = 2,563` for this subset, inside overall Microchip `S1=23,276`.
  `S1_complete=0`: Working VDD, VDDIO and analog rails remain
  **unqualified at exact-SKU applicability**, not proof those rails do
  not physically exist.

**Remaining risk requiring owner review:** The PDF p.16 is an ordering
*grammar*, not an independently enumerated manufacturer SKU table.
The `VERIFIED` decision therefore deliberately relies on **original
MCP exact commercial SKU proof + PDF explicit field-applicability rule**.
If owner interprets ADR-0002 as requiring a separate manufacturer *listing*
of every field for every exact variant, these six promotions should remain
`PARTIAL` until that higher standard is approved. CI verifies evidence
crosswalk and no missing/contradictory identity, not electrical laboratory
tests.

## IC Selector / Catalog policy boundary

ST and NXP currently display exact ICPNs in the default IC Selector after
manufacturer identity evidence and **independent Production Admission**,
even if a software-qualification profile is not `SUPPORTED`.
This existing product behavior differs from ADR-0002's accepted but
**not yet implemented** eventual `SUPPORTED-only` public-display
policy. The discrepancy must be reconciled in a separate owner-approved
policy/UI migration before Microchip's first Production admission.

This PR only extends manufacturer **Phase 1 IC Information evidence**.
No direct Production Admission, Catalog manifest/API/Selector, Job/Batch,
OpenOCD software `SUPPORTED`, Phase 2, Phase 3 or HIL change is authorized.

## Verification

Run the Microchip CFG-first workflow against all original 313 MCP
batch captures, original DFP, Chart and publisher PDF. New negative tests
reject missing or forged original SHA, unknown core/electrical field
inference, ambiguous suffixes, unsupported packages, zero/invented memory,
temperature inconsistencies, changes to the 2,563-member freeze, and
unauthorized qualification. Output is an immutable per-run Research
artifact `microchip-phase1-saml1x-exact-pdf-enriched.json`.

Source archive is temporarily retained as GitHub Actions artifacts, not
a permanent archival guarantee.
