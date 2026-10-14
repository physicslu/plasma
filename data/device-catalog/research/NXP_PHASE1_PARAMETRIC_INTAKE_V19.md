# NXP ADR-0002 Phase 1 v19 — safe offline Buy/Parametrics export intake

The NXP official **Buy/Parametrics** UI displays a **download xls**
control on various MCU family pages, e.g.
- https://www.nxp.com/products/MCX-A13X-A14X-A15X
- https://www.nxp.com/products/MCX-N94-N54-N53-N52-N24
- https://www.nxp.com/products/MCX-C15-C16

**No verified direct XLS URL or stable vendor bulk API was identified and no
official XLS bytes were acquired in this workstream. Do not invent an export
endpoint or treat an indexed/search-rendered page as an exported file.**

## Operator acquisition (manual first)

1. Open the exact official NXP product family page and select
   `Buy/Parametrics`. Use the visible **download xls** control and
   preserve the original download exactly as received. Record the page
   URL, acquisition time, and SHA256 of the original bytes.
2. If the result is a legacy `.xls`, convert a **copy** in Excel using
   `Save As → CSV UTF-8` or `XLSX`, and preserve BOTH the original
   download and converted copy and their independent SHA256 checksums.
   Do not assume a file with an .xls suffix is genuinely BIFF8 XLS.
3. Run the read-only inspector (nothing is imported into Production):

```bash
python data/device-catalog/research/nxp_phase1_parametric_ingest_v19.py \
  --input /secure/path/nxp-parametric.csv \
  --source-page 'https://www.nxp.com/products/MCX-A13X-A14X-A15X?tab=Buy_Parametric_Tab' \
  --output /tmp/nxp-parametric-review.json
```

4. Inspect each result. `EXACT_MATCH_REVIEW_ONLY` indicates that
   an original 224 admitted exact ICPN matches the vendor export *claim*,
   Flash (kB) matches the existing admitted value and SRAM is nonzero.
   This is **not** an automatic `VERIFIED` field promotion:
   independent original-byte provenance and scope review remain required.
   Flash mismatch or missing SRAM stays blocked. Export rows not in
   original admitted cohort cannot trigger identity admission.

## Supported formats / nonclaims

- Accept UTF-8 CSV and `.xlsx` without external dependencies.
  XLSX is parsed using Python standard library; no formula evaluation;
  unsafe/too-large XML and invalid or ambiguous headers fail closed.
- Legacy `.xls` is **intentionally rejected**; use the manual conversion
  workflow before parsing. HTML/XML masquerading as XLS is not reliable.
- Required manufacturer export columns: `Part`, `Flash (kB)`,
  `SRAM (kB)`. Optionally recognize `Supply Voltage [Min to Max] (V)`
  or separate Min and Max. VDD values never fill VDDA or VDDIO.
- The tool checks exact SKUs against the existing v18 224 admitted NXP
  identities and original Flash; it generates a **review-only JSON report**,
  computes a SHA256 of the actual supplied input, and does not mutate
  `data/device-catalog/production`, the research source dataset,
  software-support states or any runtime.
- CLI `--source-page` is an **operator assertion**, not proof the file
  originated from NXP. `source_authenticity=UNVERIFIED_OPERATOR_PROVIDED_FILE`
  is mandatory until independent file/source provenance review.
- Offline fixtures are synthetic only, never manufacturer evidence.

The next evidence step is obtaining the original official export bytes
(or a documented legitimate NXP source API) and verifying whether
the export's columns are consistent enough to use for automated
Phase 1 enrichment. Until then v17/v18 independently sourced
manufacturer data are retained.
