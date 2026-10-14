# Microchip Phase 1 official chart XLSX importer — Research v1

**ADR authority:** [ADR-0002 Phase 1](../../../docs/adr/0002-openocd-software-qualified-catalog-visibility.md).
**Scope:** read-only, offline, source-bound **Base Device / chart-family information**.
**Not:** an exhaustive Microchip commercial ICPN catalog, per-SKU `VERIFIED` data, OpenOCD software `SUPPORTED`, a Programming Profile, a Production admission, or PPU/HIL.

## What this implementation actually does

`microchip_phase1_chart_xlsx_v1.py` accepts an **original Microchip Parametric Search “Download Chart → All Data” XLSX** obtained by an authorized manual export; this PR does **not** claim an actual official workbook was captured. The source must be preserved externally, with its original bytes and the generated SHA-256 report. The official [Parametric Search guide DS00004852A](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/MarketCommunication/Promotions/Parametric-Search-User-Guide-00004852.pdf) describes chart-scoped exports. Such a chart is not manufacturer-wide nor necessarily an exact orderable SKU list.

The Python standard-library importer:
- Selects an **explicit worksheet** and exact **original header names** (no guessed header aliases or units).
- Reads original cell text from XLSX shared strings, inline strings or raw scalar values; **does not execute formula cells**, access external workbooks, normalize memory units or infer exact suffixes.
- Records the **original XLSX byte SHA-256**, file size, chart URL, category/chart scope, capture time, workbook sheet, original header, source row, original value and stated unit; `--verify` replays the same workbook/config/locked classification offline.
- Uses the **already reviewed OpenOCD 0.12.0 source-locked Microchip Research P0/P1 family regex leads** *only to allocate research time*: P0 first, P1 second, others P2 archive-only. A regex match is a **lead**, not a DFP exact name attestation, commercial order code, demonstrated Flash capability or software support.
- Emits chart **Base Device** observations, not exact commercial ICPNs. P0/P1 chart specifications are at most `PARTIAL`; missing values are `UNKNOWN`; P2 records retain identifiers and workbook provenance **without deep enrichment**. No `VERIFIED` is emitted.
- Writes only an explicitly supplied report path outside a `production` directory; **does not touch** Production manifests, public IC Selector/API, Microchip MCP datasets, OpenOCD binaries or socket/PPU state.

## Usage — after capturing a real original manufacturer XLSX

1. In Microchip's **official Parametric Search**, select a bounded MCU chart and export **Download Chart → All Data**. Store the original XLSX unmodified and retain the export screen/chart URL, chosen category, timestamp, relevant terms and chart context. This may require manual browser operation; **no undocumented export endpoint or bypass of a manufacturer HTTP 403 is implemented**.
2. Inspect the **actual XLSX header row and worksheet name**. Prepare a configuration file, for example (illustrative headers below are **not** verified Microchip column names):

```json
{
  "chart_url": "https://www.microchip.com/en-us/products/microcontrollers",
  "chart_scope": "Record the precise official chart/category, filters and All Data selection",
  "worksheet": "ACTUAL_EXPORTED_WORKSHEET_NAME",
  "captured_at_utc": "2026-10-14T03:30:00Z",
  "columns": {
    "base_device": {"header": "ACTUAL_DEVICE_COLUMN", "unit": null},
    "flash": {"header": "ACTUAL_FLASH_COLUMN", "unit": "KB"},
    "ram": {"header": "ACTUAL_SRAM_COLUMN", "unit": "KB"},
    "vdd": {"header": "ACTUAL_OPERATING_VOLTAGE_COLUMN", "unit": "V"}
  }
}
```

The `columns` mapping is **explicit, per chart**. Omit absent columns; do not fabricate them or assume the example headers/units apply. Supported Phase 1 mappings: `base_device`, `flash`, `ram`, `vdd`, `io_supply`, `vdda`, `package`, `pin_count`, `temperature`, `core_architecture`, `core_model`. Numeric chart values remain **raw strings**, not parsed operating ranges; the `unit` is an explicitly transcribed source unit, not an inferred conversion.

3. Process and immediately replay the same **unchanged** source file:

```bash
python data/device-catalog/research/microchip_phase1_chart_xlsx_v1.py \
  --xlsx /secure/official-microchip-original.xlsx \
  --config /secure/chart-source-and-header-map.json \
  --output /tmp/microchip-chart-phase1-research.json

python data/device-catalog/research/microchip_phase1_chart_xlsx_v1.py \
  --xlsx /secure/official-microchip-original.xlsx \
  --config /secure/chart-source-and-header-map.json \
  --verify /tmp/microchip-chart-phase1-research.json
```

4. Independently replay official **MCP exact-ordering code** evidence (where captured), cross-reference the manufacturer-reported `basePartNumber` to the chart **without modifying this chart report**, and investigate missing supply rails or variant differences using the official, revision-bound datasheet. Only **separate** reviewed per-exact-ICPN evidence may promote a corresponding Phase 1 field to `VERIFIED`; the previously merged SAMD21 two-ICPN pilot stays untouched.

## Acceptance / blockers

- **CI validates synthetic XLSX cases only.** It does **not** prove that a real, manufacturer-exported XLSX has been obtained, that the chart's header names match the example, or that the chart covers every exact Microchip ordering variant.
- Parser rejects duplicate Base Device identifiers, missing mapped headers, malformed files, overly large archives, duplicate ZIP members, XLSX formulas/external links, untrusted chart URLs, missing worksheet and a changed OpenOCD source pin. Non-ASCII part identities are not silently changed.
- Report `PARTIAL` means a chart-family **observation**, not an exact IC `VERIFIED`. P0/P1/P2 are **Research priority**, never `openocd_software_support`. Missing P0/P1 regex lead is P2 **within this bounded screen**, not proof of permanent lack of OpenOCD compatibility.
- The original XLSX remains outside the Git repository by design. Its hash alone does not archive it; provide a durable original-byte store before treating evidence as long-lived. Keep original MCP source responses and exact datasheet evidence separate. Failure to obtain a chart is `SOURCE_NOT_AVAILABLE` in acquisition tracking, **not** a zero-device result.
- Next acceptance gate is **one actual official bounded export + archived original bytes + independently replayed chart and exact manufacturer MCP crosswalk**. No automatic Production or software/hardware support promotion is authorized.
