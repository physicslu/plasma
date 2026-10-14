# ADR-0002 Microchip Phase 1 — second bounded P0 manufacturer MCP cohort

**Status:** new two-family **Research query exploration**, not approved commercial ICPN acquisition/admission or software/physical qualification.

## Source-first query choice

The previous [source-verified P0 chart → MCP pilot](MICROCHIP_PHASE1_P0_MCP_CROSSWALK_V1.md) established 341 observed chart P0 Base Devices and only one successful MCP identity replay for `ATSAMD21G18` (manufacturer query alias `ATSAMD21G18A`), yielding **23 source-observed commercial-ordering candidates**, of which only two had been separately reviewed. That does **not** license inventing order-code suffixes for the remaining 340 P0 names.

This PR reads a **new actual manufacturer chart source** from `https://www.microchipdirect.com/chart.aspx?branchID=21&mid=3`, verifies its archived original bytes and SHA-256 using existing source replayers, and deterministically selects the **first lexicographic Base Device matching the pinned P0 lead** in each of **two** source-backed groups:

- `sam-e5-d5` — Cortex-M4 family lead, research only
- `pic32mx` — MIPS M4K family lead, research only

These are deliberately **exploratory queries exactly matching manufacturer chart Base Device text**. They are **not previously approved query/base alias mappings** and have not established an exact commercial ICPN. All source results are quarantined unless the full `partNumber` passes the existing exact-query-boundary check, contains an ordering suffix (not the bare query), and manufacturer `basePartNumber` matches **the original chart Base Device exactly**. Even source-observed matching candidates remain `SOURCE_OBSERVED_NOT_REVIEWED` and `NOT_ADMITTED`; no exact datasheet specs are promoted.

The pinned source lead is OpenOCD **0.12.0** commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`. **P0 is not software SUPPORTED.** This workflow does **not** program, erase, verify or read any target device.

## Audit and failure isolation

`microchip_phase1_p0_second_cohort_v1.py` reuses existing `microchip_phase1_p0_chart_batch_v1.py` (real chart original-byte SHA-256 replay), `microchip_mcp_paged_probe_v2.py` (official MCP, independently reconciled complete 20/60 pagination) and `microchip_phase1_p0_mcp_crosswalk_v1.py` (source-file SHA-256/identity extraction).

**Do not treat query completion as a manufacturer SKU census.** Both queries are bounded by original MCP 600-row safety limit. Each can independently fail with `SOURCE_NOT_AVAILABLE` (HTTP/timeout, zero or oversized result, inconsistent pagination, altered MCP schema, etc.). No retry-loop scraping, alternate endpoint guessing or global catalog enumeration is implemented. Original bytes and partial failed-capture manifests are retained where present. The flow never invents a zero exact-ICPN count when the source failed or was never queried.

A 341-row P0 matrix distinguishes:

| State | Semantics |
| --- | --- |
| `CURRENT_REPLAYED_MATCH` | Original source and both pagination walks passed, and one or more exact-query-boundary rows match the chart `basePartNumber`; still research-only |
| `CURRENT_REPLAYED_NO_EXACT_MATCH` | Original source/pagination passed but no joined order code passed this narrow query, **not** evidence that the chip lacks orderable variants |
| `SOURCE_NOT_AVAILABLE` | Query was attempted, but complete original evidence could not be confirmed; **number of ICPNs UNKNOWN** |
| `PREVIOUS_REPLAYED_NOT_RECHECKED` | The earlier SAMD21 pilot is historical evidence, **not replayed in the current capture** |
| `NOT_QUERIED` | No evidence acquired in this iteration; **number of ICPNs UNKNOWN** |

An explicit per-query report contains chart name/row/original SHA-256, MCP source evidence manifest hash, original MCP page reference and SHA-256 for any observed candidate, fuzzy-result count, mismatch quarantines, field qualification flags, and separate coverage states. The only semantic proof in this PR is the **identity source-row relationship**; Flash/RAM/VDD and per-variant package/temperature/rails remain subject to Phase 1 evidence review.

## Reproducible CLI

```bash
python data/device-catalog/research/microchip_phase1_chart_html_source_v1.py \
  --capture /tmp/microchip-p0-second-original-chart

python data/device-catalog/research/microchip_phase1_p0_second_cohort_v1.py \
  --chart-original-root /tmp/microchip-p0-second-original-chart \
  --plan /tmp/microchip-p0-second-query-plan.json
```

Use **only the two `mcp_search_term` values in that emitted source-locked plan**, not a guessed part number:

```bash
python data/device-catalog/research/microchip_mcp_paged_probe_v2.py \
  --query "EXACT_PLANNED_CHART_BASE_NAME" \
  --output-dir /tmp/microchip-second-query-source

python data/device-catalog/research/microchip_mcp_paged_probe_v2.py \
  --query "EXACT_PLANNED_CHART_BASE_NAME" --replay \
  --output-dir /tmp/microchip-second-query-source
```

Then run the combined script with corresponding `--e5-original-root` / `--pic32-original-root`, `--e5-outcome REPLAYED` / `--pic32-outcome REPLAYED` and `--report`; independently recompute the exact report using `--verify`. If source capture fails, pass `--e5-outcome SOURCE_NOT_AVAILABLE` or `--pic32-outcome SOURCE_NOT_AVAILABLE` **without an original source root**. The dedicated CI automates this selection and captures at most two original official MCP queries.

## Live manufacturer source-replay observation — 2026-10-14

The actual GitHub Runner completed the two independent manufacturer MCP captures and both full original-source replays successfully. The [run 38528439094](https://github.com/physicslu/plasma/actions/runs/38528439094) archived the original source bytes, SHA-256 manifests, chart-derived selection plan and 341-row Research matrix in [artifact 11876777831](https://github.com/physicslu/plasma/actions/runs/38528439094/artifacts/11876777831).

| Pinned P0 research lead | Original manufacturer chart Base Device / MCP query | Source-observed exact-ordering candidates | Classification |
| --- | --- | ---: | --- |
| `sam-e5-d5` | `ATSAMD51G18A` | **10** | `CURRENT_REPLAYED_MATCH`; source-observed, **not** individually reviewed |
| `pic32mx` | `PIC32MX110F016B` | **14** | `CURRENT_REPLAYED_MATCH`; source-observed, **not** individually reviewed |
| **This bounded cohort** | **2 original chart Base Devices** | **24** | **Research only, no admission** |

The original MicrochipDirect chart SHA-256 in this capture was `3fccf5773f1137b057f0bee48919a07d0015b5b6ef5b0c27f8177b4e001ab0a7`. This is a *new* dynamically generated source response, not required to hash identically to previous manufacturer captures. Each MCP original response's own SHA-256 and pagination manifest are recorded inside the artifact.

The 341-row P0 state matrix after this live experiment is **2 `CURRENT_REPLAYED_MATCH`**, **1 `PREVIOUS_REPLAYED_NOT_RECHECKED`** (SAMD21 from PR #871), **338 `NOT_QUERIED`**, **0 `SOURCE_NOT_AVAILABLE`**, and **0 `CURRENT_REPLAYED_NO_EXACT_MATCH`**. Prior SAMD21's **23** exact-prefix source candidates were **not re-queried in this run**. Thus 24 is the **new** source-observed cohort only; neither 24 nor any sum of cohorts is a manufacturer-wide SKU coverage denominator or OpenOCD-supported list.

Original artifact expiration: **2027-01-12 07:27:29 UTC**. Original-response retention beyond this 90-day Artifact remains **NOT VERIFIED**. No exact commercial ICPN was admitted and no Phase 1 family memory, voltage, package or temperature value was automatically promoted to a per-commercial-part `VERIFIED` field.

## Durable original-byte custody gate (not yet satisfied)

The GitHub Actions artifact retains original chart/MCP bytes, `manifest.json`, SHA-256 hashes, chart-derived plan and combined report for **90 days**. Before permanent admission, an operator must copy the original artifact **unchanged** into a durable, versioned, access-controlled archive; preserve its content hash, source URL/query, capture timestamp and provenance; configure retention and object integrity checks; and independently **replay the original bytes** from that archive. GitHub artifact URLs alone and SHA-256 references without the original byte content do **not** establish durable evidence.

A future archive pipeline must avoid including API credentials or private headers; the existing MCP scripts record read-only request metadata and product responses. This PR does **not** connect to a durable archive service and must not claim long-lived evidentiary custody.

## Explicit non-goals

Zero Production Catalog or public IC Selector/API/UI writes; zero exact commercial ICPN admission; zero Flash/Programming Profile/OpenOCD software qualification; zero PPU/Socket/HIL, FPGA, firmware or Job/Batch changes. P1 remains deferred, P2 archive-only. No manufacturer-global ICPN denominator is known.
