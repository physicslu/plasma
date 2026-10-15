# Microchip P1 — ADR-0002 Phase 1 exact ICPN information ledger v1

**Research-only, P1 priority.** This workflow is authorized to work on **126 Microchip exact manufacturer ICPNs**, but **P1 does not mean Phase 1**, and does not mean that the OpenOCD Target CFG can write Flash. The accepted [ADR-0002](../../../docs/adr/0002-openocd-software-qualified-catalog-visibility.md) makes the broad Phase 2 Programming scope active for other work; this bounded P1 manufacturer-information project remains **Phase 1 data only**.

## What advances from P0 into the P1 cohort

The original-source-replayed manufacturer MCP/DFP Research crosswalk covers 23,276 exact manufacturer commercial candidate ICPNs and classifies:

| Source-replayed Research priority | Distinct exact commercial ICPNs | Scope |
| --- | ---: | --- |
| P0 | 2,437 | Retained separately, **not** reclassified as P1 |
| **P1** | **126** | SAM L1x Target-only `tcl/target/atsaml1x.cfg` family evidence |
| Not matched by these bounded CFG leads | 20,713 | Not automatically unsupported or nonexistent |
| **Total original-source-replayed subset** | **23,276** | Not the same full denominator as historical 24,051 research aggregate |

The P1 regex is pinned to **ATSAML1 / SAML1 (SAM L10/L11)**; **SAM L21/L22 are not automatically members of this P1 source-locked CFG cohort**. Never enlarge the 126-ICPN source set merely because another Microchip SAM L family has a datasheet.

The P1 `atsaml1x.cfg` is from the **OpenOCD 0.12.0 source-pinned Target-only research lead** (pinned source commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`). The original DFP source contains **12** P1 candidate support names, which is **not the same unit** as 126 commercial order codes. The 126 original MCP rows must have an exact `basePartNumber` ↔ original DFP name match. There is no evidence-authorized name trimming, generic family alias, Flash Driver, `SUPPORTED`, or physical readiness claim.

## Source-evidence acceptance

The `microchip_phase1_p1_information_ledger_v1.py` projection requires a reconstructed, source-pinned full original MCP/DFP `microchip_openocd_reverse_coverage_v1.py` report, preserving exact commercial `partNumber`, source-provided `basePartNumber`, original MCP response SHA-256, DFP identity and Target-only CFG. No missing source is silently filled in from an OpenOCD CFG name.

For each of the **13 ADR-0002 IC Information fields**:

- `manufacturer`, exact `icpn`, original `base_device`: **VERIFIED identity** from independently replayed original manufacturer MCP responses, with exact ICPN and original response SHA-256.
- Package, Pin Count, Flash, RAM, Working VDD, Temperature, Core Model: family-level `PARTIAL` **only when** a source-exact matching manufacturer Base Device is found in the independently replayed **original MicrochipDirect 32-bit Chart** and the chart actually includes that column/value.
- I/O Supply, VDDA, Core Architecture: `UNKNOWN` until separate official manufacturer evidence exists.
- Other missing or inaccessible chart information: `UNKNOWN`, never zero, never a guessed commercial suffix or `VERIFIED` based on family data.

The existing parametric Chart source is a **chart-specific HTML snapshot**, not a universal source census or a revisioned datasheet. `p1_deferred_base_names` in the existing P0 chart parser are intentionally deferred: the P1 script independently binds their original HTML table row ordinal, column name and value before any `PARTIAL` field is created. No incorrect family-to-exact promotion is permitted.

## Actual original-source replay result — 2026-10-15

The real GitHub-hosted, offline original-byte replay of **all 13 Microchip MCP archives**, the official DFP original index, and the 32-bit MicrochipDirect Chart original HTML produced the following results in [CI run 38672984714](https://github.com/physicslu/plasma/actions/runs/38672984714):

- **126** original-MCP exact commercial `partNumber` records with individually source-replayed `basePartNumber` and `atsaml1x.cfg` Target-only CFG Research link.
- **12 distinct original manufacturer Base Devices**, which match **12 original DFP P1 names** and **12 original MicrochipDirect Chart P1 Base Device rows**.
- **126/126 Base Device ↔ chart row links; 0 chart-absent exact ICPNs**. The seven source-observed chart fields **Package, Pin Count, Flash, RAM, Working VDD, Temperature, Core Model are all PARTIAL for 126 exact ICPNs**; none are exact-order-code VERIFIED from the parametric chart.
- **Manufacturer, ICPN and Base Device: VERIFIED for 126** each. **I/O Supply, VDDA and Core Architecture: UNKNOWN for 126** each.
- **Record-level Phase 1 fully verified: 0; software SUPPORTED: 0; Production/Selector admission: 0.**

**Official document for the next evidence acquisition:** Microchip [SAM L10/L11 Family Data Sheet, DS60001513G](https://ww1.microchip.com/downloads/en/DeviceDoc/SAM-L10L11-Family-Data-Sheet-DS60001513G.pdf), **Section 2 Ordering Information (datasheet page 16)**. The section explains the manufacturer's ordering-code conventions (family/series, pin group, Flash density, package/temperature grade and carrier). These conventions are a *research lookup aid*, **not authority to invent an exact ICPN or promote any field without the original PDF bytes, complete existing manufacturer order code and documented applicability**.

**PDF status:** reference located, **original PDF bytes have NOT been archived and independently replayed into the PLASMA Research evidence vault in this PR**. Accordingly this PR contains **no new PDF-derived VERIFIED field**, no exact ordering-table claim and no vendor Programming Profile. Preserve the existing 126 manufacturer-MCP identities and their chart PARTIAL state until a dedicated reviewed PDF evidence enrichment PR.

## P1 Phase 1 next evidence acquisition

1. Acquire the Microchip **official SAM L10/L11 Family Data Sheet, DS60001513G** (https://ww1.microchip.com/downloads/en/DeviceDoc/SAM-L10L11-Family-Data-Sheet-DS60001513G.pdf) and any other officially required revision strictly matched to the 126 P1 Base Devices; use its **Ordering Information** section, in source-original bytes; record document identity, published revision, retrieval URL, original SHA-256, source date, table/page, field/units and exact ICPN applicability.
2. Verify each complete ordering code and its package/temperature against the exact manufacturer-MCP `partNumber`; do not infer ordering suffix semantics or backfill unrelated variants.
3. Verify family Flash, RAM, working VDD, I/O Supply, VDDA, Temperature, CPU model and conditional electrical limits from official datasheet tables; separate base-level `PARTIAL` from exact-order-code `VERIFIED`, and keep `UNKNOWN`/ `CONFLICT` when source evidence is lacking.
4. Submit source-enrichment as a **separate research PR** with independent PDF original-byte replay, exact-source SHA verification, negative tests for revision/identity/units mismatch, record-level claim controls, and counts that never silently change the 126/2,437 denominators.
5. Keep **Production Catalog/IC Selector and Phase 2 Programming** completely unchanged until their own approval/qualification gates. A Phase 1 identity ledger is not a software support qualification.

## Source-replay CI and artifacts

The existing `Microchip CFG-first Phase 1 Reverse Coverage` CI job downloads all 13 original MCP research source archives, the original DFP index, and the approved 32-bit Chart original HTML bundle. It reconstructs the 23,276 commercial rows, runs the P0 original-source validation unchanged, then generates the P1 **126-row identity and per-field evidence ledger**, grouped by manufacturer Base Device and with original-source SHA-256 and exact commercial ICPN on every record. The P1 result includes a separate chart-matching coverage count, unresolved ICPN list and field-level `VERIFIED/PARTIAL/UNKNOWN/CONFLICT` counts.

```bash
python -m unittest discover -s data/device-catalog/research \
  -p 'test_microchip_phase1_p1_information_ledger_v1.py' -v

python data/device-catalog/research/microchip_phase1_p1_information_ledger_v1.py \
  --upstream-cfg-report /path/to/original-source-replayed/microchip-full-reverse.json \
  --chart-original-root /path/to/verified-official-chart-original \
  --output /path/to/new/research/microchip-p1-phase1-information.json
```

Only the GitHub Actions original-byte replay validates these counts against actual archived manufacturer source; synthetic unit tests are not primary evidence. Even a green CI result **does not imply an official PDF has been captured or exact fields verified**, nor does a 90-day CI Artifact replace durable/offsite evidence custody.
