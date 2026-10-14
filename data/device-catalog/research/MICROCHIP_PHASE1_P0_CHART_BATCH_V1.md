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

## CI evidence and next gate

The dedicated GitHub Actions workflow `device-catalog-microchip-phase1-p0-chart-batch-v1.yml` runs synthetic negative tests and (separately) one live source capture plus independent replay. CI will archive the original HTML, manifest and chart-scoped coverage JSON for **90 days**. A green offline test does not prove live acquisition; check `Live official chart capture` and `Live P0 batch source replay` outcomes and the original-byte artifact explicitly.

Next engineering approval gates: durable manufacturer original-byte retention, an independently replayed MCP exact-ordering crosswalk beyond the two existing pilot ICPNs, precise per-variant package/temperature and missing VDDIO/VDDA datasheet review, and new chart categories for absent P0 families. No Production / public Catalog, Phase 2 Programming/OpenOCD support, Phase 3 PPU/Site/Socket/HIL, FPGA firmware or Job/Batch changes are authorized.
