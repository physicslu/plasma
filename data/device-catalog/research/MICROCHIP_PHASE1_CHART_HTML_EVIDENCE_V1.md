# Microchip Phase 1 — official MCU chart original HTML and source-bound family fields

**Authority:** [ADR-0002 Phase 1](../../../docs/adr/0002-openocd-software-qualified-catalog-visibility.md). **State:** manufacturer original HTML successfully captured and replayed; **exact commercial ICPN admission NOT authorized**.

## Source evidence (real GitHub Runner, 2026-10-14)

- Official public source: [MicrochipDirect MCU parametric chart](https://www.microchipdirect.com/chart.aspx?branchID=21&mid=3), **chart-specific subset**, not a complete commercial-SKU census.
- Reproducible capture: [GitHub Actions run 38511528729](https://github.com/physicslu/plasma/actions/runs/38511528729) and [original archive artifact 11869184417](https://github.com/physicslu/plasma/actions/runs/38511528729/artifacts/11869184417).
- Original HTML **5,735,822 bytes**, SHA-256 **`11b7ad01d672e5a9555b09871e4d166efba146b4f4bc8db3f2c39ef4257ce251`**. This digest is **one immutable capture**, not a guarantee that future dynamically served HTML has the same bytes.
- The source-byte audit and header-to-row semantic replay **PASS**. The chart's targeted base-device row `ATSAMD21G18` was parsed from original table row 103 using 33 matching headers and data cells. Different captures may change row ordinals; never treat the ordinal as stable without the original digest.
- Original CI evidence archive is configured for **90 days**, currently expires **2027-01-12 04:28:04 UTC**. A **durable independent original-byte archive** remains outstanding; GitHub Actions artifacts are not permanent custody.

## Observed Base Device data — exact original chart values

| Phase 1 field | Original official chart column / value | Research status |
| --- | --- | --- |
| Base Device | `Device Name` → `ATSAMD21G18 [More Info]` | `PARTIAL` chart family |
| Core | `CPU` → `Cortex-M0+` | `PARTIAL` |
| Flash | `Flash (KB)` → `256` | `PARTIAL`, 256 KB |
| RAM | `RAM (KB)` → `32` | `PARTIAL`, 32 KB |
| Working VDD | `Operation Voltage Range` → `1.62V - 3.63V` | `PARTIAL`, 1.62–3.63 V |
| Family temperature envelope | `Temperature Range` → `-40 to 125` | `PARTIAL`, **not every ordering suffix's rated range** |
| Pin count | `Pin count` → `48` | `PARTIAL` family-chart value |
| Family package choices | `Packages` → `45/WLCSP 48/TQFP 48/VQFN` | `PARTIAL`; not exact variant's package |
| I/O and analog supply | Not a separately established chart column | `UNKNOWN` **in this chart**; existing versioned datasheet evidence is a separate family-level source |

**Crucial mapping:** the independent official MCP original response for the existing two reviewed commercial parts, `ATSAMD21G18A-MU` and `ATSAMD21G18A-MF`, provides manufacturer `basePartNumber = ATSAMD21G18` (source-reviewed in prior PR #862). The chart replay joins on that **reviewed Base Device** rather than guessing from the ordering suffix. The chart CI step does **not** re-download/replay the MCP original bytes; this distinction is retained in the derived report.

The two **exact variants have different prior documented temperature ranges**: `-MU` -40 to +85°C, `-MF` -40 to +125°C. Thus the chart family envelope **must not** overwrite either exact part. No chart row independently proves precise exact-SKU pin/package values. Likewise, `P0` from version-pinned OpenOCD 0.12.0 is a **research-priority lead**, **not** software `SUPPORTED` and does not authorize Phase 2 qualification.

## Executable audit

```bash
# Capture from the allowlisted manufacturer chart and preserve original bytes.
python data/device-catalog/research/microchip_phase1_chart_html_source_v1.py \
  --capture /tmp/microchip-chart-original

# Byte integrity verification; this alone does not verify Flash/RAM semantics.
python data/device-catalog/research/microchip_phase1_chart_html_source_v1.py \
  --replay /tmp/microchip-chart-original

# Show safely bounded raw row/header observations without interpreting fields.
python data/device-catalog/research/microchip_phase1_chart_html_row_probe_v1.py \
  --original-root /tmp/microchip-chart-original \
  --report /tmp/microchip-chart-rows.json

# Replay the header alignment and extract PARTIAL family fields only.
python data/device-catalog/research/microchip_phase1_chart_semantics_v1.py \
  --original-root /tmp/microchip-chart-original \
  --output /tmp/microchip-chart-family-phase1.json
```

Offline unit tests use *synthetic* HTML and reject tampered SHA-256, missing/ambiguous header contracts, duplicate family row, invalid electrical units/ranges and silent elevation to software support or Production. Passing synthetic unit tests alone **never** means a live manufacturer capture passed; the dedicated CI checks live canary outcomes separately.

## Non-claims and next acceptance gates

1. Original chart **family fields** are `PARTIAL`, even when the byte/source/column alignment is reproducible. Only later reviewed, exact commercial ordering-code sources and applicable documentation can yield a `VERIFIED` exact-ICPN field.
2. This chart is a read-only manufacturer HTML alternative useful **before a true Parametric Search All Data XLSX export is captured**; it does not prove an undocumented chart export API exists. Preserve the actual XLSX raw bytes separately when available.
3. The [officially documented Product Data API](https://www.microchip.com/designresources/PartnerDataExchange/ProductAPI-user-guide.html) was **unusable in the current Runner**: its request landed at `www.microchipdirect.com/404`. That failure is captured in the other PR workflow artifact, without inventing rows or interpreting `404` as absence of a silicon device. Official MCP remains the verified live exact-commercial-ID route.
4. Next: durable source archive, read-only chart-to-MCP crosswalk with original MCP bytes, further **P0 Base Devices before P1**, per-field gap/conflict counts and a separately reviewed identity-admission decision.
5. No Production Catalog, public IC Selector/UI/API, programming/OpenOCD qualification (Phase 2), Socket/PPU/HIL (Phase 3), firmware, FPGA or Job/Batch execution change occurs in this PR.
