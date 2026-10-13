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

Microchip's [Product Selection Tools page](https://www.microchip.com/en-us/products/selection-tools) links Parametric Search and MAPS. The public Parametric Search page is an interactive application and its indexed output is not enough to establish an exhaustive count. A more promising bulk source is Microchip's official [Product Data API guide](https://www.microchip.com/designresources/PartnerDataExchange/ProductAPI-user-guide.html): the GET API accepts a product/base-part query, supports pagesize/pagenumber pagination, and returns totalRecords/totalPages plus exact part_number, base_part_number, package_type, pin_count, lifecycle_status, projected_eol_date and product_url fields. The current official guide shows inconsistent illustrative examples: one query example is followed by an 11-record response whose sample row is PIC10F200, while another pagination example shows 10 PIC10F202 records and five pages at page size 2. Do not use either illustrated count as an expected population. A fixed, read-only workflow is configured to probe the documented PIC10F202 query, validate pagination totals and exact-part uniqueness, and upload raw responses with hashes. The probe was attempted from GitHub Actions four times on 2026-10-13; the latest request received HTTP 200 with a 15,516-byte HTML page instead of JSON (SHA-256 `6e361146ff5be8084825c352283e1a8ddb0367aa704aa31297ab27d6f75b9a22`). It failed closed and produced no product records. The workflow is manual-only while this endpoint behavior is unresolved, and its artifact retains the raw response for diagnosis. Gate 2a is therefore incomplete; the probe has not yet validated pagination or SKU uniqueness and does not establish the exhaustive MCU/DSC family set or lifecycle semantics.

The API guide shows raw lifecycle_status values such as REL and EOL but does not define their semantics in the documented response field list. An exact orderable SKU example is marked EOL even though the broader PIC10F202 product page says In Production; this is a warning that family-level product status cannot substitute for SKU-level status. Keep raw API status values until their mapping is independently confirmed. Product pages also expose human-readable statuses, including In Production for PIC16F18855/ATmega4809 and Not Recommended for new designs for PIC24FJ128GA606.

Gate 1 confirms that the official guide documents a paginated exact-part search endpoint. Its examples are not a reliable count oracle. The endpoint's live response remains unresolved because the CI request returned HTML, so no live response totals have been validated. Gate 1 **does not prove that every MCU/DSC family has been enumerated, that a family query returns every orderable SKU, or that product-family leaf counts reconcile**. The family inventory must be built independently, API pagination validated per family, and lifecycle codes reconciled before any global Active denominator is reported.


## Gate 1b — source-surface audit (partial; 2026-10-13)

A second inspection checked the manufacturer landing surfaces rather than treating their headings as a complete device population. The [8-bit PIC page](https://www.microchip.com/en-us/products/microcontrollers/8-bit-mcus/pic-mcus) and [AVR page](https://www.microchip.com/en-us/products/microcontrollers/8-bit-mcus/avr-mcus) render narrative/featured-family content, not a complete family table with a reconciled total. The [16-bit page](https://www.microchip.com/en-us/products/microcontrollers/16-bit-mcus) exposes PIC24F GA and GB family links and mentions GC and DA in application groupings, but does not enumerate PIC24 plus dsPIC family membership. The [32-bit PIC32/SAM page](https://www.microchip.com/en-us/products/microcontrollers/32-bit-mcus/pic32-sam) groups PIC32C and SAM and links PIC32CX/SAM collateral, but does not provide a complete leaf-family or exact-SKU table; PIC32M needs a separate inventory. The [32-bit AVR/RISC page](https://www.microchip.com/en-us/products/microcontrollers/32-bit-mcus/avr-risc-mcus) does not establish complete family membership or counts and overlaps legacy SAM discovery. The [wireless MCU page](https://www.microchip.com/en-us/products/microcontrollers/wireless) explicitly presents modules and SoCs together, so module-vs-IC classification and overlap reconciliation are required.


The 16-bit page also links an official [PIC24 MCU Peripheral Integration Quick Reference Guide](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/Brochures/30010109.pdf) (DS30010109L, 2022). Its selector table provides useful PIC24 base-pattern discovery seeds (for example PIC24F and PIC24EP rows), but it is a feature quick-reference, not a current lifecycle inventory, and it does not close the dsPIC lane. Record guide revision/date and use it only to seed the official API family query matrix.


### Family query seeds recorded (not an exhaustive inventory)

The source registry now records evidence-backed family labels to seed later API queries. Microchip Developer Help groups 8-bit PICs by baseline/mid-range/enhanced/high-end architecture and documents the 10F/12F/16F, 12F1/16F1 and PIC18 structures; current AVR discovery seeds include tinyAVR/ATtiny, megaAVR/ATmega, XMEGA and DA/DB/DD/EA/EB/SD. The current DSC surface identifies dsPIC33A/C/E and related dsPIC33EV material; older dsPIC30 and dsPIC33F official product records remain discovery seeds. For 32-bit devices, Microchip identifies PIC32MM/MX/MK/MZ and separately PIC32C/CX; SAM pages expose several SAM letter/number families. The legacy AVR/RISC page explicitly lists AVR32, Arm7 and SAM3. Wireless candidates include PIC32-BZ6, PIC32CX-BZ2/WBZ451, PIC32CX-BZ3/WBZ351, PIC32-BW1 and WFI32. These labels and source links are stored under `family_query_seeds` in the JSON registry; they are not exact SKUs, do not establish query-string semantics, and may overlap lanes.

This closes only the surface review. The observed family names are discovery seeds, not an exhaustive inventory; no live Product Data API response fixture or reconciled per-family API page totals are committed. Keep `population_boundary_validated=false` and `global_active_denominator=null`. Next, obtain the official Product Selector/MAPS export or another complete manufacturer family listing, freeze the base-part query set with source hashes, then capture every API page per base part and compare returned `totalRecords`/`totalPages` against fetched rows and unique exact `part_number` values. Preserve raw lifecycle codes until their official mapping is established.

## Alternative source continuation — 2026-10-13

The [alternative source audit](MICROCHIP_ALTERNATIVE_SOURCES_V1.md) records
four complementary official routes: public no-authentication MCP, Parametric
Search XLSX export, versioned Device Family Packs, and PCN/EOL attachments.
It includes a bounded list of 27 distinct PIC10/PIC12 DFP discovery names and
ten indexed PIC10F206 catalog-part candidates. Direct page retrieval omitted
the latter table, so the ten strings remain unverified candidates. Neither
list is an Active denominator or an admission snapshot. MCP initialization, six-tool discovery and one two-row PIC10F202 response
have now succeeded from the execution environment. A subsequent complete
capture was blocked by a cancelled network approval before any response bytes
were obtained. `microchip_mcp_probe_v1.py` now enforces source-byte digests, MCP method and
request sequence, strict pagination and page-size 2 vs 60 reconciliation.
The bounded PIC10/PIC12 batch reconciled 26 of 27 queries, producing 347
unique exact-prefix SKU candidates. The missing `PIC12F529T48A` query returned
MCP NOT_FOUND; its official product page separately labels the device End of Life.
These bounded results do not establish manufacturer-wide completeness or
readiness for Production. See the alternative audit for
commands and the exact evidence boundary.

## Gate 0 — implemented

microchip_bulk_coverage_v1.py validates the segment registry and optional manufacturer evidence snapshots. It verifies exact part identifiers, allowed lifecycle vocabulary, official Microchip hostnames, per-row evidence SHA-256, duplicate rows, and cross-lane lifecycle conflicts. A snapshot can be marked complete only with matching official row count and a source-content digest. Even that does not establish a Microchip-wide denominator: the registry keeps population_boundary_validated=false, so global denominator and coverage remain null.

The workflow runs deterministic contract tests only. It does not scrape live pages or change Production.

Run locally:

```bash
python data/device-catalog/research/microchip_bulk_coverage_v1.py
python -m unittest discover -s data/device-catalog/research -p 'test_microchip_bulk_coverage_v1.py'
```

## Gate 1c — deterministic DFP batching plan (offline only)

`microchip_mcp_batch_plan_v1.py` replays the archived original Microchip DFP
index through `archived_inventory()`, checks its source digest against the frozen
registry fingerprint, validates per-pack and per-lane totals, and emits stable
3- or 10-name **query plans** with SHA-256 query-list digests. It explicitly
separates syntactically unsupported device names (manual mapping required) and
excluded/unclassified packs; none are silently turned into made-up orderable
SKUs. An empty discovery lane is **not** proof that the product category is
empty. No MCP traffic, lifecycle inference or Production writes are performed.

Once the original DFP artifact is available locally:

```bash
python data/device-catalog/research/microchip_mcp_batch_plan_v1.py \
  --evidence-root /path/to/official-dfp-index-archive \
  --output /tmp/microchip-dfp-research-batch-plan.json \
  --batch-size 10
```

This plan is a staged research queue, not permission to launch all vendor
queries. The separate 27-query pilot still has one official EOL/NOT_FOUND
exception and the current MCP probe stops for any query reporting more than 60
results. Scaling capture requires explicit bounded scheduling, retry and
high-result-count reconciliation before network execution.

## Gate 2b — bounded over-60 result reconciliation (v2)

`microchip_mcp_paged_probe_v2.py` introduces an independent and fully
replayable **20-per-page vs 60-per-page** double walk, supporting 1–600 reported
text-search matches per query. Both walks must cover every page and report the
same exact `partNumber`, `basePartNumber` and **raw** `lifecycleStatus`
for each record; missing, duplicated, reordered or drifting pages fail closed.
Every source byte and exact handshake/request sequence is SHA-256 archived.
A query reporting more than 600 matches is intentionally rejected for manual
re-scoping. No zero-result or NOT_FOUND response is admitted as proof of EOL.

The v1 2-vs-60 pilot format remains available and is not reinterpreted as v2.
This is an **offline contract-tested implementation**, not evidence that the
live Microchip service supports such wide queries consistently. Live execution
must be staged and raw artifacts retained before making source claims.

```bash
python data/device-catalog/research/microchip_mcp_paged_probe_v2.py \
  --query PIC10F202 --output-dir /tmp/microchip-v2-single-query
python data/device-catalog/research/microchip_mcp_paged_probe_v2.py \
  --query PIC10F202 --output-dir /tmp/microchip-v2-single-query --replay
```

## Gate 2c — Pilot batch/ledger v2 integration

The original 27-name PIC10/PIC12 batch driver can now explicitly use
`--capture-format paged_v2` to collect both complete pagination walks for
queries reporting 61–600 rows. The default remains `v1` for backward
compatibility. Offline batch replay and the source-linked ledger detect the
archived schema (v1 or v2), preserve the original response-byte digest for
each SKU candidate, and reject unrecognized formats. V2 ledger rows are
derived from the primary 20-row capture only, after independent 60-row
reconciliation succeeds. Tests use synthetic 75-result archives; **no live
>60-result manufacturer observations have yet been claimed**.

```bash
python data/device-catalog/research/microchip_mcp_batch_v1.py \
  --output-dir /tmp/microchip-mcp-v2-capture --max-queries 3 \
  --workers 1 --capture-format paged_v2
python data/device-catalog/research/microchip_mcp_batch_v1.py \
  --output-dir /tmp/microchip-mcp-v2-capture --max-queries 3 --replay
```

## Gate 2d — one approved batch at a time

`microchip_mcp_plan_capture_v1.py` independently regenerates the entire
DFP query plan from the original archived official index, verifies the
registry-pinned SHA-256 and exact plan equality, and selects exactly one
3- or 10-query batch by its deterministic ID. It rejects forged/reordered
plans, unsafe batch IDs, Production paths and existing live-capture targets.
All new live calls explicitly require `--capture`, use v2 two-walk
pagination, and write a batch source attestation. Without `--capture` it
only replays an already attested archive and fails closed on tampering.

```bash
# Live capture is EXPLICIT and limited to the selected batch.
python data/device-catalog/research/microchip_mcp_plan_capture_v1.py \
  --evidence-root /path/to/original-dfp-index \
  --plan /tmp/microchip-dfp-research-batch-plan.json \
  --batch-id 8bit-0001 --output-root /tmp/microchip-research-batches \
  --workers 1 --capture

# Default, safer mode: offline replay. No --capture flag.
python data/device-catalog/research/microchip_mcp_plan_capture_v1.py \
  --evidence-root /path/to/original-dfp-index \
  --plan /tmp/microchip-dfp-research-batch-plan.json \
  --batch-id 8bit-0001 --output-root /tmp/microchip-research-batches
```

Offline unit tests exercise the gate with synthetic source inventories;
they are not confirmation of a completed real-source bulk run.

## Manual GitHub Actions capture limits

`.github/workflows/device-catalog-microchip-mcp-batch-v1.yml` remains
`workflow_dispatch` **only** (never runs vendor API calls from a PR check).
It exposes a `capture_format` choice. `paged_v2` defaults to **3**
queries, allows at most **10**, uses one MCP session at a time, and uploads
raw bytes even when any query fails. The historical `v1` path retains
the old 27-query option. The workflow may need default-branch registration
before GitHub exposes Run Workflow. Workflows alone do not prove a live
successful capture; inspect the resulting archive and replay summary.

## Gate 2e — source-attested multi-batch offline rollup

`microchip_mcp_batch_rollup_v1.py` independently rebuilds the DFP batch plan
from the pinned original index and replays **each present batch** using the
original MCP evidence bytes, not cached batch summaries. A missing batch is
`not_captured`; missing/tampered attestations, query failures, source-byte
mismatches or incomplete archives quarantine the **entire batch**.
Candidates from complete batches are deduplicated by exact ordering part
number, retaining all source SHA-256 links. Cross-batch raw lifecycle
disagreements quarantine the **identity** and surface a conflict report.
All candidate and batch totals remain Research-only; even a fully replayed DFP
queue cannot establish Microchip's commercial Active SKU denominator.

```bash
python data/device-catalog/research/microchip_mcp_batch_rollup_v1.py \
  --evidence-root /path/to/original-dfp-index \
  --plan /tmp/microchip-dfp-research-batch-plan.json \
  --batch-root /tmp/microchip-research-batches \
  --output /tmp/microchip-research-rollup.json
```

Use `--require-all` only when the entire planned research queue has been
captured. CI covers synthetic successful 75-record archives, missing/tampered
archives, forged plans, and conflicts. No live vendor bulk dataset was
acquired by this offline rollup.

## Negative MCP HTTP response retention

The shared v1/v2 MCP HTTP client now preserves bounded original **4xx/5xx**
response bytes and SHA-256 alongside the attempted request, even when
`urllib` raises `HTTPError`. The query still fails closed: a failed
capture lacks a complete transcript and cannot enter the evidence ledger,
rollup or Production. The original error body is diagnostic evidence only;
HTTP 404, MCP `NOT_FOUND`, and an EOL **device page** do not independently
prove a particular ordering SKU is EOL. Unit tests use a synthetic HTTP 404
body, not a newly captured live error response.

## Evidence artifact retention and permanent archival gap

Future GitHub Actions uploads from the two Microchip manual API/MCP probe
workflows now request **90-day** Artifact retention rather than 7 days,
subject to GitHub repository policy limits. This setting is **not retroactive**
and does not rescue earlier one-time captures; the DFP HTML index and PIC10/
PIC12 raw pilot evidence currently referenced only by Actions artifact URLs
must be independently copied to an approved durable evidence store with
original byte hashes **before those historical artifacts expire**.

An SHA-256 printed in PR documentation is not a replacement for the original
archived source bytes. Do not mark a Research Gate, a global coverage
denominator, or any Production row as supported by missing or expired
original evidence. This PR does not contain a full raw manufacturer archive.

## Next gates

1. **Finish Gate 1b: family inventory.** Obtain a complete official Product Selector/MAPS family listing or equivalent, enumerate manufacturer family leaves within each lane, document overlaps/exclusions, and freeze the base-part query set with retrieval timestamps and hashes. Landing pages alone are not exhaustive.
2. **Gate 2a/2b: authoritative product API and MCP coverage.** The separately documented official Product Data API route returned HTTP 200 HTML rather than JSON; it is still not a validated bulk population source. The independent Microchip MCP route did establish a 26/27 PIC10/PIC12 bounded pilot, with one official device-level EOL/NOT_FOUND exception. Offline-tested v2 now reconciles complete 20- and 60-row pagination walks for at most 600 matches; obtain original live >60-result fixtures and review exact query semantics before promoting coverage claims. Keep all raw lifecycle values. **Gate 2c/2d: staged batch execution.** The manual workflow supports v1 or v2; v2 only permits 3 or 10 pilot queries and does not grant automatic bulk capture.
3. **Gate 3: exact-set gap report.** Compute observed Active identities against Production with exact set arithmetic. Keep partial families explicitly partial whenever an official denominator cannot be proven.
4. **Gate 4: metadata and admission proposals.** Replay official orderable tables and datasheets for package, temperature range, memory and other required fields. Preserve existing Production rows byte-for-byte. Freeze a small family-wise postimage and validator.
5. **Gate 5: Production publication.** Requires separate explicit owner approval, deterministic postimage, all catalog/API/UI CI and reviewed final diff. Runtime mappings, electrical profiles and physical qualification remain separate claims.

No step in this foundation reads a target, changes hardware, alters programming permissions, performs flash operations, or modifies Production catalog files.
