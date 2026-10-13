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

Microchip's [Product Selection Tools page](https://www.microchip.com/en-us/products/selection-tools) links Parametric Search and MAPS. The public Parametric Search page is an interactive application and its indexed output is not enough to establish an exhaustive count. A more promising bulk source is Microchip's official [Product Data API guide](https://www.microchip.com/designresources/PartnerDataExchange/ProductAPI-user-guide.html): the GET API accepts a product/base-part query, supports pagesize/pagenumber pagination, and returns totalRecords/totalPages plus exact part_number, base_part_number, package_type, pin_count, lifecycle_status, projected_eol_date and product_url fields. The official example query for PIC10F202 returns 11 exact records. This can provide package-level exact ordering codes and lifecycle evidence without crawling every individual product page.

The API guide shows raw lifecycle_status values such as REL and EOL but does not define their semantics in the documented response field list. An exact orderable SKU example is marked EOL even though the broader PIC10F202 product page says In Production; this is a warning that family-level product status cannot substitute for SKU-level status. Keep raw API status values until their mapping is independently confirmed. Product pages also expose human-readable statuses, including In Production for PIC16F18855/ATmega4809 and Not Recommended for new designs for PIC24FJ128GA606.

Gate 1 confirms a scalable exact-SKU acquisition endpoint, but **does not yet prove that every MCU/DSC family has been enumerated, that the query returns every orderable SKU, or that product family leaf counts reconcile**. The family inventory must be built independently, API pagination validated per family, and lifecycle codes reconciled before any global Active denominator is reported.


## Gate 1b — source-surface audit (partial; 2026-10-13)

A second inspection checked the manufacturer landing surfaces rather than treating their headings as a complete device population. The [8-bit PIC page](https://www.microchip.com/en-us/products/microcontrollers/8-bit-mcus/pic-mcus) and [AVR page](https://www.microchip.com/en-us/products/microcontrollers/8-bit-mcus/avr-mcus) render narrative/featured-family content, not a complete family table with a reconciled total. The [16-bit page](https://www.microchip.com/en-us/products/microcontrollers/16-bit-mcus) exposes PIC24F GA and GB family links and mentions GC and DA in application groupings, but does not enumerate PIC24 plus dsPIC family membership. The [32-bit PIC32/SAM page](https://www.microchip.com/en-us/products/microcontrollers/32-bit-mcus/pic32-sam) groups PIC32C and SAM and links PIC32CX/SAM collateral, but does not provide a complete leaf-family or exact-SKU table; PIC32M needs a separate inventory. The [32-bit AVR/RISC page](https://www.microchip.com/en-us/products/microcontrollers/32-bit-mcus/avr-risc-mcus) does not establish complete family membership or counts and overlaps legacy SAM discovery. The [wireless MCU page](https://www.microchip.com/en-us/products/microcontrollers/wireless) explicitly presents modules and SoCs together, so module-vs-IC classification and overlap reconciliation are required.


The 16-bit page also links an official [PIC24 MCU Peripheral Integration Quick Reference Guide](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/Brochures/30010109.pdf) (DS30010109L, 2022). Its selector table provides useful PIC24 base-pattern discovery seeds (for example PIC24F and PIC24EP rows), but it is a feature quick-reference, not a current lifecycle inventory, and it does not close the dsPIC lane. Record guide revision/date and use it only to seed the official API family query matrix.

This closes only the surface review. The observed family names are discovery seeds, not an exhaustive inventory; no live Product Data API response fixture or reconciled per-family API page totals are committed. Keep `population_boundary_validated=false` and `global_active_denominator=null`. Next, obtain the official Product Selector/MAPS export or another complete manufacturer family listing, freeze the base-part query set with source hashes, then capture every API page per base part and compare returned `totalRecords`/`totalPages` against fetched rows and unique exact `part_number` values. Preserve raw lifecycle codes until their official mapping is established.

## Gate 0 — implemented

microchip_bulk_coverage_v1.py validates the segment registry and optional manufacturer evidence snapshots. It verifies exact part identifiers, allowed lifecycle vocabulary, official Microchip hostnames, per-row evidence SHA-256, duplicate rows, and cross-lane lifecycle conflicts. A snapshot can be marked complete only with matching official row count and a source-content digest. Even that does not establish a Microchip-wide denominator: the registry keeps population_boundary_validated=false, so global denominator and coverage remain null.

The workflow runs deterministic contract tests only. It does not scrape live pages or change Production.

Run locally:

```bash
python data/device-catalog/research/microchip_bulk_coverage_v1.py
python -m unittest discover -s data/device-catalog/research -p 'test_microchip_bulk_coverage_v1.py'
```

## Next gates

1. **Finish Gate 1b: family inventory.** Obtain a complete official Product Selector/MAPS family listing or equivalent, enumerate manufacturer family leaves within each lane, document overlaps/exclusions, and freeze the base-part query set with retrieval timestamps and hashes. Landing pages alone are not exhaustive.
2. **Gate 2: bounded live acquisition.** After family inventory is frozen, query the documented Product Data API per base part, capture every page and verify page counts/unique exact part numbers; only then build a pinned-URL, read-only acquisition matrix in GitHub Actions. Capture raw HTML/JSON, retrieval time, page/count evidence and row hashes before interpretation. Upload run artifacts; no PR-controlled arbitrary URLs.
3. **Gate 3: exact-set gap report.** Compute observed Active identities against Production with exact set arithmetic. Keep partial families explicitly partial whenever an official denominator cannot be proven.
4. **Gate 4: metadata and admission proposals.** Replay official orderable tables and datasheets for package, temperature range, memory and other required fields. Preserve existing Production rows byte-for-byte. Freeze a small family-wise postimage and validator.
5. **Gate 5: Production publication.** Requires separate explicit owner approval, deterministic postimage, all catalog/API/UI CI and reviewed final diff. Runtime mappings, electrical profiles and physical qualification remain separate claims.

No step in this foundation reads a target, changes hardware, alters programming permissions, performs flash operations, or modifies Production catalog files.
