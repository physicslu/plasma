# Microchip ICPN Bulk Acquisition — ST-style Segmented Plan v1

**Status:** research-only foundation. **Date:** 2026-10-13. **Authority:** no Production admission or Programming Backend authorization.

## Method carried forward from ST

The high-volume workflow is: official manufacturer population discovery, parallel segment capture, exact-set reconciliation, manufacturer-evidence metadata replay, bounded admission proposals, explicit owner-approved Production publication, and separate backend qualification. The Microchip catalog must keep those gates independent.

Microchip is not ST. Its official MCU discovery is organized across 8-bit PIC/AVR, 16-bit PIC24/dsPIC, 32-bit PIC32/SAM, 32-bit AVR/RISC, and wireless MCU surfaces. Product pages and parametric search are discovery surfaces; this work has **not** established that they provide a single exhaustive set or a consistent manufacturer lifecycle denominator. Exact ordering codes and lifecycle status must come from auditable official product records.

The existing research OpenOCD target catalog has 234 Microchip identifiers. These are target/device discovery candidates, not exact commercial ordering codes, lifecycle evidence, or a Microchip coverage denominator. Production ICPN data is read from the current manifest by the validator; the research count is not assumed to equal Production.

## Five acquisition lanes

The machine-readable source map is microchip-bulk-source-registry-v1.json:

1. 8-bit PIC and AVR MCUs.
2. 16-bit PIC24 MCUs and dsPIC DSCs.
3. 32-bit PIC32 and SAM Arm MCUs.
4. 32-bit AVR and RISC MCUs.
5. Wireless MCUs and SoCs.

Some products may appear in more than one manufacturer surface. Reconcile by exact ordering part number, preserve each evidence source, and fail on contradictory lifecycle observations. Microprocessors, FPGA, analog, power, memory, interface and timing products are outside this MCU/DSC effort or need a separately named project scope.

## Gate 1 — initial official source audit

The official Microchip [MCU landing page](https://www.microchip.com/en-us/products/microcontrollers) exposes separate 8-bit, 16-bit and 32-bit navigation. Its [8-bit MCU page](https://www.microchip.com/en-us/products/microcontrollers/8-bit-mcus) groups PIC and AVR. The [16-bit page](https://www.microchip.com/en-us/products/microcontrollers/16-bit-mcus) describes PIC24; the old microcontrollers-and-microprocessors route redirects there. The [32-bit Arm page](https://www.microchip.com/en-us/products/microcontrollers/32-bit-mcus/pic32-sam) groups PIC32C and SAM. The separate [32-bit AVR/RISC page](https://www.microchip.com/en-us/products/microcontrollers/32-bit-mcus/avr-risc-mcus) also includes legacy AVR32, Arm7 and SAM3 product families, so exact identifiers may overlap between discovery lanes. The [wireless MCU page](https://www.microchip.com/en-us/products/microcontrollers/wireless) covers both MCU ICs and modules; module-only products must not be admitted as ICs without an explicit scope decision.

Microchip's [Product Selection Tools page](https://www.microchip.com/en-us/products/selection-tools) links both Parametric Search and MAPS. The public Parametric Search page is an interactive application and the indexed page currently exposes no-product/empty states; this is not evidence of a complete product count or lifecycle facet. Gate 1 therefore confirms useful official discovery routes but **does not yet validate exhaustive family leaves, orderable SKU counts, or a common lifecycle schema**. No global Active denominator is supportable yet.

## Gate 0 — implemented

microchip_bulk_coverage_v1.py validates the segment registry and optional manufacturer evidence snapshots. It verifies exact part identifiers, allowed lifecycle vocabulary, official Microchip hostnames, per-row evidence SHA-256, duplicate rows, and cross-lane lifecycle conflicts. A snapshot can be marked complete only with matching official row count and a source-content digest. Even that does not establish a Microchip-wide denominator: the registry keeps population_boundary_validated=false, so global denominator and coverage remain null.

The workflow runs deterministic contract tests only. It does not scrape live pages or change Production.

Run locally:

```bash
python data/device-catalog/research/microchip_bulk_coverage_v1.py
python -m unittest discover -s data/device-catalog/research -p 'test_microchip_bulk_coverage_v1.py'
```

## Next gates

1. **Gate 1b: source-surface audit.** Enumerate manufacturer family leaves within each lane, verify lifecycle vocabulary and pagination/count semantics, inspect Product Selection/MAPS export behavior, document overlaps and exclusions, and freeze evidence with retrieval timestamps and hashes.
2. **Gate 2: bounded live acquisition.** After source audit, build a pinned-URL, read-only Playwright/HTTP matrix in GitHub Actions. Capture raw HTML/JSON, retrieval time, page/count evidence and row hashes before interpretation. Upload run artifacts; no PR-controlled arbitrary URLs.
3. **Gate 3: exact-set gap report.** Compute observed Active identities against Production with exact set arithmetic. Keep partial families explicitly partial whenever an official denominator cannot be proven.
4. **Gate 4: metadata and admission proposals.** Replay official orderable tables and datasheets for package, temperature range, memory and other required fields. Preserve existing Production rows byte-for-byte. Freeze a small family-wise postimage and validator.
5. **Gate 5: Production publication.** Requires separate explicit owner approval, deterministic postimage, all catalog/API/UI CI and reviewed final diff. Runtime mappings, electrical profiles and physical qualification remain separate claims.

No step in this foundation reads a target, changes hardware, alters programming permissions, performs flash operations, or modifies Production catalog files.
