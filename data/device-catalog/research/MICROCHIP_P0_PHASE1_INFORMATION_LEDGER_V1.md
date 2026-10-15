# Microchip P0 — ADR-0002 Phase 1 exact-ICPN information ledger v1

**Status:** 2,437 exact commercial research ICPNs selected from fully replayed 23,276-source cohort. This is a **Research-only evidence coverage ledger**, NOT a completed Phase 1 or Production Catalog admission. No programming test, Flash Driver analysis or Phase 2/3 modification.

## Selector visibility (verified from repository)

`software/web/app/devices/ic-selector.tsx` searches the Production `/api/devices/search` interface, whose catalog manifest is `data/device-catalog/production/icpn-v1-manifest.json`. At this revision, the Production manifest contains only STMicroelectronics and NXP sources, **zero Microchip entries**. The 2,437 Research ICPNs are consequently **not available** through the default IC Selector. This is a repository state check, not an assertion that every independently deployed instance runs the same revision.

ADR-0002 explicitly reserves default Product Selector publication for **Phase 2 software `SUPPORTED`** qualification. Even internal identity admission alone does not authorize default user selection. Do not quietly add a `Microchip` entry to the manifest or relax Selector criteria as part of this Phase 1 research work.

## Exact source gate

Upstream: `microchip_openocd_reverse_coverage_v1.py` replays the original manufacturer DFP HTML and 13 disjoint original Microchip MCP archives. Historical original query audit: **321 observed directories / 313 source-attested / 8 quarantined**, **23,276 distinct source-replayed ICPNs**. Of these, **2,414 exact DFP↔manufacturer-MCP-base CFG candidates and 23 manufacturer-reviewed SAMD21 aliases** form the **2,437 P0** cohort.

Each ICPN row has separately preserved source-replayed `partNumber` and `basePartNumber` plus original Microchip MCP response SHA-256 reference. DFP/CFG linkage is **Research priority metadata** and never qualifies software support. The projection code itself consumes the upstream report; it does **not independently replay original manufacturer bytes**, and records that fact explicitly. The workflow generates the source-replayed upstream file immediately before this projection, tests it twice and publishes both.

## Current Phase 1 field completeness (13 fields)

The first three fields are source-linked identity observations; the other ten are **UNKNOWN** pending independently replayed official manufacturer exact-variant specifications, chart-cell applicability and datasheets.

| Field | VERIFIED | PARTIAL | UNKNOWN | CONFLICT |
| --- | ---: | ---: | ---: | ---: |
| Manufacturer | 2,437 | 0 | 0 | 0 |
| Exact ICPN | 2,437 | 0 | 0 | 0 |
| Base Device (`basePartNumber`) | 2,437 | 0 | 0 | 0 |
| Package | 0 | 0 | 2,437 | 0 |
| Pin Count | 0 | 0 | 2,437 | 0 |
| Flash | 0 | 0 | 2,437 | 0 |
| RAM | 0 | 0 | 2,437 | 0 |
| Working VDD | 0 | 0 | 2,437 | 0 |
| I/O Supply | 0 | 0 | 2,437 | 0 |
| VDDA | 0 | 0 | 2,437 | 0 |
| Temperature | 0 | 0 | 2,437 | 0 |
| Core Architecture | 0 | 0 | 2,437 | 0 |
| Core Model | 0 | 0 | 2,437 | 0 |

**Zero records have completed Phase 1 information evidence or internal Catalog admission.** Verified original `basePartNumber` does not prove flash/RAM/package voltage information, and a family datasheet without demonstrated exact commercial variant applicability may reach at most `PARTIAL` where supported.

This deliberately conservatively classifies all unjoined Phase 1 values `UNKNOWN`. Some previous Microchip SAMD21 bounded research already includes certain **PARTIAL** family-level fields; this full 2,437-row ledger does **not** silently import the earlier two-row pilot as independently replayed exact commercial evidence. Pilot evidence should be merged in a distinct, keyed and source-replayed Phase 1 enrichment batch.

### P0 CFG group sizes (Research candidate only)

| CFG | Exact research ICPNs |
| --- | ---: |
| `at91samdXX.cfg` | 667 |
| `atsame5x.cfg` | 354 |
| `atsamv.cfg` | 175 |
| `pic32mx.cfg` | 1,241 |
| **Total P0** | **2,437** |

Other OpenOCD P0 CFG leads currently show no exact ICPN match in this historical Research cohort, which is a **source-bound discovery gap, not proof that no suitable chips exist**. The 126 P1 target-only and 20,713 unresolved Research ICPNs remain outside this P0 field ledger.

## Precise remaining work to close this P0 Phase 1 cohort

1. **Source-acquire** chart scopes, official manufacturer exact SKU ordering tables and datasheet revisions for all four priority groups. Preserve original bytes, SHA-256 and manufacturer source identity, not a scraped numeric summary.
2. **Bind Package, Pin Count and Temperature** from original manufacturer exact order-code records or explicitly applicable ordering tables, with row/page locator. If unavailable, mark UNKNOWN; never infer package from commercial suffix.
3. **Bind Flash, RAM, Working VDD, VDDIO and VDDA**, preserving original source units/rail names, conditions, source version and exact-vs-family applicability. Distinguish VDDCORE from VDDA and I/O supplies. Family-only source evidence cannot be `VERIFIED` for an exact ICPN.
4. **Bind optional Core architecture/model** only from official source and separately evidence it. Treat missing applicable core-model data as UNKNOWN rather than copying OpenOCD Target configuration.
5. Reconcile all **13 fields × 2,437 exact ICPNs**. Produce per-field state counts and original source locators, quarantine contradictions, maintain per-ICPN internal admission `NOT_ADMITTED` until independently reviewed, and obtain separate Production/Phase 2 approval before any product visibility change.

**Stop conditions:** no source → UNKNOWN; conflicting manufacturer evidence → CONFLICT; source scope limited to family → PARTIAL; exact-variant applicability proven from official source → VERIFIED. No fabricated field or automatic data promotion. All Phase 2 Programming, OpenOCD flash software qualification, PPU/Socket/FPGA/HIL, runtime changes, and public Catalog/Selector publication are explicitly excluded from this task.

## Offline/CI verification

The new `microchip_phase1_p0_information_ledger_v1.py` consumes the original-byte-source-replayed upstream Research mapping report and creates 2,437 evidence ledgers, 13-field gap counts, per-CFG gap matrix, provenance SHA links and all independent qualification/admission flags false.

~~~bash
python -m unittest discover -s data/device-catalog/research \
  -p 'test_microchip_phase1_p0_information_ledger_v1.py' -v

python data/device-catalog/research/microchip_phase1_p0_information_ledger_v1.py \
  --upstream-cfg-report /path/to/source-replayed/microchip-full-reverse.json \
  --output /path/to/new/research/microchip-p0-phase1-information-ledger.json
~~~

For real manufacturer original-byte validation, run the existing `Microchip CFG-first Phase 1 Reverse Coverage` GitHub workflow. Its full-batch job retrieves the 13 historical archives, independently replays the original Microchip vendor responses and generates both the source-replayed 23,276-row upstream report and the new 2,437-row Phase 1 field evidence ledger. GitHub CI artifacts still expire in 90 days; this does not satisfy the separate durable custody gate.
