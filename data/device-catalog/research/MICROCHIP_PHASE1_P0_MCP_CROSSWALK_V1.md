# Microchip ADR-0002 Phase 1 — P0 chart × original MCP commercial ICPN crosswalk v1

**Research-only evidence contract.** This iteration connects the [341 observed P0 manufacturer-chart Base Devices](MICROCHIP_PHASE1_P0_CHART_BATCH_V1.md) to a **single already reviewed** Microchip official MCP `search_products` pilot query (`ATSAMD21G18A`). It does not make 341 manufacturer MCP queries, infer suffixes, populate Production, or qualify OpenOCD software/FPGA/PPU hardware.

## Why the source join is not a string trim

Microchip's independent MCP `partNumber` is the **complete manufacturer-reported commercial identifier**, while `basePartNumber` is the **manufacturer-reported base identity**. The official chart calls its family row `ATSAMD21G18`, while already reviewed source query `ATSAMD21G18A` and order codes `ATSAMD21G18A-MU`/`-MF` use an extra suffix. Inferring every orderable variant by appending/truncating characters would fabricate identity links. The bounded v1 allows only this prior-reviewed query/base pair, source-locked through the existing two-ICPN Phase 1 pilot. New P0 pairs require separate documented review before expanding requests.

The importer uses the **existing** `microchip_phase1_p0_chart_batch_v1.py` original-HTML SHA-256 replay and `microchip_mcp_paged_probe_v2.py` original-response, complete dual 20/60 independent pagination validation. It then re-reads **original primary MCP response bytes** and extracts the exact `partNumber`, `basePartNumber`, lifecycle and response-file hash/array locator for each source-row. The two approved pilot codes are independently checked with `microchip_phase1_mcp_identity_v1.py`.

A row joins to the P0 chart only if the complete `partNumber` matches the previously reviewed query **on an ordering-code boundary**, is **not the bare base query**, and the original `basePartNumber` exactly matches the chart Base Device. Rows with a conflicting manufacturer base part or an ambiguous bare query are quarantined, not silently mapped; unrelated fuzzy hits remain excluded. Newly observed codes, if any, are merely `ORIGINAL_MANUFACTURER_EXACT_ORDERING_OBSERVED_NOT_REVIEWED`, not admitted, not exact specification-complete, and not software-supported.

## Chart cohort and denominator

| Population / concept | Meaning |
| --- | --- |
| **341 P0 Base Devices** | Original official MCU HTML chart rows classified by pinned OpenOCD 0.12.0 **research leads**; this is the fixed v1 chart-scope denominator, not all manufacturer parts |
| **1 reviewed MCP query** | Prior-reviewed `ATSAMD21G18A` query, matched to chart `ATSAMD21G18` by manufacturer evidence, if original bytes successfully replay |
| **340 others** | `NOT_QUERIED` if the one MCP query succeeds; no zero-part or negative OpenOCD support conclusion is permitted |
| **SOURCE_NOT_AVAILABLE** | A query was attempted but manufacturer original bytes, response completeness or replay did not pass; the affected Base Device's exact ICPN coverage is **unknown**, not zero |
| **Source-derived commercial codes** | Chart-scoped, exact `partNumber` source rows that pass independent pagination and raw-base crosswalk; a searchable result is never guaranteed to be all commercial SKUs, current-active production, or PLASMA-supported ICs |

The report separately retains `mcp_source_state_by_chart_base_device`, chart P0 `PARTIAL/UNKNOWN` field statuses, source hashes, raw exact-product rows, quarantined identity mismatches, and the already-reviewed two-pilot identities. It explicitly sets all admission, Catalog publishing, software programming and physical HIL claims to **false**. A chart family voltage, memory, temperature or package option **never becomes exact-ICPN VERIFIED** through this crosswalk. Per-suffix temperature and electrical rail conditions still require separately applicable official ordering/datasheet evidence.

## Repeatable usage

Capture one *new* original manufacturer chart and read-only MCP query through approved, documented scripts:

```bash
python data/device-catalog/research/microchip_phase1_chart_html_source_v1.py \
  --capture /tmp/microchip-p0-original-chart

python data/device-catalog/research/microchip_mcp_paged_probe_v2.py \
  --query ATSAMD21G18A \
  --output-dir /tmp/microchip-p0-original-mcp-ATSAMD21G18A

python data/device-catalog/research/microchip_phase1_p0_mcp_crosswalk_v1.py \
  --chart-original-root /tmp/microchip-p0-original-chart \
  --mcp-original-root /tmp/microchip-p0-original-mcp-ATSAMD21G18A \
  --mcp-outcome REPLAYED \
  --output /tmp/microchip-p0-original-crosswalk.json

python data/device-catalog/research/microchip_phase1_p0_mcp_crosswalk_v1.py \
  --chart-original-root /tmp/microchip-p0-original-chart \
  --mcp-original-root /tmp/microchip-p0-original-mcp-ATSAMD21G18A \
  --mcp-outcome REPLAYED \
  --verify /tmp/microchip-p0-original-crosswalk.json
```

For a baseline **without network/MCP capture**, set `--mcp-outcome NOT_RUN` and omit `--mcp-original-root`. For a separately documented manufacturer capture failure, set `--mcp-outcome SOURCE_NOT_AVAILABLE`; do not pass purported original MCP data. The CI runs synthetic negative cases plus a real bounded official chart/MCP canary. The MCP step's `continue-on-error` protects the offline code review, **not** a claim that live source acquisition succeeded. Judge capture validity from its individual step outcome and response artifact.

**Evidence custody:** GitHub Actions stores original HTML/MCP response bytes and SHA-256 manifests for **90 days**, which is **not** a permanent, version-locked archive. Long-lived evidence preservation, manufacturer MCP coverage beyond this one query, and its exact variant gaps remain separate gates.

## First real official manufacturer query result — 2026-10-14

**Manufacturer original-byte replay PASS:** [GitHub Actions run 38521157253](https://github.com/physicslu/plasma/actions/runs/38521157253); [original chart + full dual-paginated MCP responses + 341-row JSON coverage artifact 11873762953](https://github.com/physicslu/plasma/actions/runs/38521157253/artifacts/11873762953).

- Current original official MicrochipDirect chart SHA-256: `d295b1057594f77a05798afd46d569b0985dd141c59b3af8d1f09bfba041a069` (different original response capture from PR #868; dynamic manufacturer HTML, not a conflicting specification).
- Reviewed single manufacturer search: `ATSAMD21G18A`, source-verified chart Base Device `ATSAMD21G18`.
- Original MCP `search_products` result: **24 observed rows; 23 exact-query-prefix commercial ordering-code candidates; 1 unrelated fuzzy result excluded**. Every linked commercial candidate preserved as **`NOT_ADMITTED`**. Of the 23 candidates, the two previously reviewed exact pilot identities `ATSAMD21G18A-MU` and `ATSAMD21G18A-MF` were independently replayed, leaving **21 additional source-observed exact-ordering candidates not individually reviewed**. Manufacturer base mismatch quarantine count in this capture: **0**.
- Chart P0 denominator states: **1 `MCP_ORIGINAL_IDENTITY_REPLAYED`**, **340 `NOT_QUERIED`**, **0 `MCP_SOURCE_NOT_AVAILABLE`**. This does **not** demonstrate 1/341 OpenOCD support, 23 active SKUs, or manufacturer-wide coverage.
- Original response/manifest and source SHA-256 per raw MCP page are kept in the CI artifact; the workflow artifact currently expires **2027-01-12 06:15:31 UTC**. It is a **90-day temporary archive**. Independent durable source retention remains a blocker for irreversible Catalog admission.
- Base Device/chart family Flash/RAM/VDD evidence stays `PARTIAL`; exact commercial part variant package, pin count, rated temperature and separate VDDIO/VDDA applicability still require their own precise manufacturer evidence. No Phase 2/3 qualification, production write or public selector change is authorized.

## Safety and scale-up criteria

Before allowing further P0 queries, require: (1) one observed chart Base Device, (2) an explicit documented query name and manufacturer ordering evidence, (3) independent complete MCP pagination and source hash replay, (4) mismatch quarantine and identity/variant distinction, and (5) a per-chart-family denominator report marking unqueried names. No undocumented MCP enumeration, fuzzy-name auto-promotion, blind mass scraping, Phase 2 Flash programming verification or Phase 3 hardware qualifications are allowed.

**Next engineering increment:** propose a small additional query cohort selected from already observed P0 chart families and review the actual manufacturer base/device mapping, then expand P0 source evidence in bounded steps with detailed coverage and conflicts.
