# Microchip ADR-0002 Phase 1 — OpenOCD-first P0 chart batch v1

**Scope:** source-locked **manufacturer Base Device Research** only. **Not** exact commercial ICPN enumeration, admission, programming support or physical compatibility.

## Source and priority contract

- The only live chart in this bounded step is the [official MicrochipDirect 32-bit MCU chart](https://www.microchipdirect.com/chart.aspx?branchID=21&mid=3) (`branchID=21&mid=3`). Manufacturer HTML is archived as **original bytes with SHA-256**, then replayed offline before any field extraction.
- The original chart is manufacturer **family/Base Device** information. It is not the full Microchip ordering catalog, does not prove historical/EOL coverage and is not an XLSX export. The earlier two exact ordering parts `ATSAMD21G18A-MU` and `ATSAMD21G18A-MF` are linked only through their **previously reviewed** MCP `basePartNumber=ATSAMD21G18` evidence. This batch does **not** independently replay the MCP bytes or admit these two parts.
- Use pinned **OpenOCD 0.12.0 source commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`** and repository `microchip-openocd-first-source-lock-v1.json` P0 and P1 research regex to allocate investigation resources. For chart device identities matching **exactly one P0 lead**, collect the Phase 1 information cells; **P1 names are deferred**; unmatched names **P2 archived** with their original row locator only.
- **Caution:** a P0/P1 pattern is a bounded, static OpenOCD source **research lead**, not a DFP device-identity attestation, precise part-number-to-silicon proof or `software_support=SUPPORTED`. P2 here is an archive-only queue, not proof that OpenOCD cannot program the device.

## Reproducible original-byte workflow

```bash
python data/device-catalog/research/microchip_phase1_chart_html_source_v1.py \
  --capture /tmp/microchip-chart-phase1-original

python data/device-catalog/research/microchip_phase1_p0_chart_batch_v1.py \
  --original-root /tmp/microchip-chart-phase1-original \
  --output /tmp/microchip-phase1-p0-chart-report.json

python data/device-catalog/research/microchip_phase1_p0_chart_batch_v1.py \
  --original-root /tmp/microchip-chart-phase1-original \
  --verify /tmp/microchip-phase1-p0-chart-report.json

python -m unittest discover -s data/device-catalog/research \
  -p 'test_microchip_phase1_p0_chart_batch_v1.py' -v
```

Only an existing, independently source-replayed archive is accepted; any checksum mismatch fails. `--verify` recomputes the deterministic report from the same raw HTML/lock/approved pilot and rejects a changed report.

## Data classification and coverage reports

- **P0 Base Device**: original chart row name, source HTML digest and row/column locators, source-locked lead ID, `core_model`, Flash, RAM, working VDD, package options, chart pin count and *family temperature envelope*. Each successfully parsed value is **`PARTIAL`**; blank, invalid or absent values remain **`UNKNOWN`** with raw text and reason. Units follow exact official headers, e.g. `Flash (KB)`, `RAM (KB)`, `Operation Voltage Range`. No memory-unit conversion is inferred. I/O supply and VDDA are always `UNKNOWN` **from this chart**, and must be sourced separately from applicable datasheet rails.
- **P1**: source-scope name and row locator only; no Phase 1 family deep enrichment in this iteration.
- **P2**: cheap archive with original name/row; never synthesize Flash/RAM, silicon support or lifecycle.
- Coverage denominators are **observed Base Device chart rows**, grouped by OpenOCD research lead and by field `PARTIAL/UNKNOWN`; `VERIFIED` and `CONFLICT` counts here remain 0 because no exact commercial-ICPN field is qualified. Do **not** extrapolate the counts to 24,051 Microchip Research candidates, 3,717 DFP names, all active products or PLASMA supported parts.
- Any duplicate chart Base Device, malformed source, ambiguous/missing header, modified OpenOCD pin, inconsistent prior SAMD21 pilot data or missing previously replayed `ATSAMD21G18` row **fails closed**. Format-dependent raw electrical fields that cannot be parsed stay `UNKNOWN` without suppressing the rest of the bounded chart; original text is retained.

## First live source-replay result — 2026-10-14

**Observed original manufacturer source (chart-scoped, not all Microchip devices):** [run 38512477006](https://github.com/physicslu/plasma/actions/runs/38512477006), [raw HTML + deterministic coverage report artifact 11870247005](https://github.com/physicslu/plasma/actions/runs/38512477006/artifacts/11870247005).

- Original HTML: **5,735,943 bytes**, SHA-256 **`720597e331082be39f22ffed622718e3bfe172de8cfd354b0be3a421faead67f`**; independently replayed before classification. This capture is a *new* live response and need not have the identical hash of earlier, dynamically generated chart pages.
- Original HTML contains 724 `tr` nodes; after chart structure/identity validation, **703 distinct observed Base Device** rows, **341 P0**, **12 P1 deferred**, **350 P2 archived**, one excluded non-identity/wrong-width row. These are chart row counts, **not exact orderable commercial ICPNs**.
- P0 research group rows: `pic32mx=112`, `sam-d-c-r-l0=78`, `sam-e5-d5=25`, `sam-v70-e70-s70=33`, `sam3=33`, `sam4-except-l=25`, `sam4l=18`, `sam7=17`. The missing `atmega128-limited` lead is not a negative support finding: this particular MCU chart does not cover all manufacturer product categories.
- P0 chart field quality: **Flash 341 PARTIAL / 0 UNKNOWN; RAM 340 PARTIAL / 1 UNKNOWN; VDD 341 PARTIAL / 0 UNKNOWN; Core 341 PARTIAL / 0 UNKNOWN; temperature, chart pin count and package-choice fields each 341 PARTIAL / 0 UNKNOWN; I/O Supply and VDDA each 0 PARTIAL / 341 UNKNOWN**. No field may be promoted to exact commercial-ICPN `VERIFIED` by this chart alone.
- **0 exact ICPN field verifications; 0 admissions; 0 software support qualifications; no Production changes.** The existing separate two-ICPN SAMD21 pilot remains Research-only.
- Original-source artifact expiration: **2027-01-12 04:39:00 UTC**. A durable original-byte archive and independent full MCP crosswalk still need implementation.

**Denominator integrity:** the previous version-pinned DFP Research snapshot classified **364 P0 support names**, a different population from these **341 chart Base Device rows**. Neither `341/364` nor `341/24,051` is a valid Microchip support/coverage percentage. Do not conflate chart availability with DFP support-name coverage or exact commercial order-code qualification.

## CI evidence and next gate

The dedicated GitHub Actions workflow `device-catalog-microchip-phase1-p0-chart-batch-v1.yml` runs synthetic negative tests and (separately) one live source capture plus independent replay. CI will archive the original HTML, manifest and chart-scoped coverage JSON for **90 days**. A green offline test does not prove live acquisition; check `Live official chart capture` and `Live P0 batch source replay` outcomes and the original-byte artifact explicitly.

Next engineering approval gates: durable manufacturer original-byte retention, an independently replayed MCP exact-ordering crosswalk beyond the two existing pilot ICPNs, precise per-variant package/temperature and missing VDDIO/VDDA datasheet review, and new chart categories for absent P0 families. No Production / public Catalog, Phase 2 Programming/OpenOCD support, Phase 3 PPU/Site/Socket/HIL, FPGA firmware or Job/Batch changes are authorized.
