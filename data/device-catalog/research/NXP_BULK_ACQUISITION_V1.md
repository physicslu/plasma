# NXP ICPN Bulk Acquisition — ST-style Segmented Plan v1

**Status:** research-only infrastructure. **Date:** 2026-10-12. **Authority:** no Production admission or Programming Backend authorization.

## What ST actually did

The final ST process was `official exhaustive Active snapshot -> parallel segment acquisition -> exact set intersection/difference -> source-evidence-locked metadata replay -> bounded admission proposal -> explicit owner-approved Production publication -> separate OpenOCD runtime evaluation`. Official ST eStore provided four parent STM32 segments with trustworthy live Marketing Status facets and page counts, allowing exact reconciliation of 4,550 Active devices. The final ST 9-device write only occurred after explicit approval and verified that existing identity bytes were unchanged.

NXP is **not** ST: its Arm MCU index is distributed among MCX, Kinetis, LPC, K32, i.MX RT crossover and wireless product-family pages. The existing KL25 Playwright capture reads exact Active identities from NXP's Package/Quality table, but does not establish the completeness of other families or the entire manufacturer.

## Bounded v1 scope and six parallel acquisition lanes

See `nxp-bulk-source-registry-v1.json` for the official NXP index entrypoints:

1. MCX
2. Kinetis
3. LPC
4. K32
5. i.MX RT crossover MCU
6. Wireless MCU

S32K/S32M automotive, NXP application processors, 8/16-bit MCU and unrelated analog/power devices are **deferred explicitly**. These source surfaces can share family aliases: deduplication is on *exact orderable identifier* and lifecycle conflicts are hard errors.

**Do not assume** a single NXP-wide eStore card index, ST's four-category denominator, or a numerical expected source count before independent official evidence. Every lane must first discover an authoritative manufacturer family/product index; then enumerate complete package/quality SKU rows and official lifecycle states. Keep source URL, timestamp, official page/pagination/count evidence when present, and per-row content SHA-256. Capture raw HTML/DOM as run artifacts **before interpreting** rows. If source completeness cannot be established, report partial/blocked rather than silently treating visible rows as a full population.

## Research-only reconciliation Gate 0 (implemented)

`nxp_bulk_coverage_v1.py` checks six-segment policy, verifies retained KL25 12 exact research identities and content digest, reads the current Production manifest, and reconciles optional per-segment manufacturer-evidence JSON snapshots. It refuses invented lifecycle tokens, duplicate part numbers within a lane, cross-lane lifecycle conflicts, missing content hashes and non-NXP evidence URLs. A lane cannot claim completeness without an independently captured manufacturer facet count and full family enumeration evidence. The v1 registry intentionally has `population_boundary_validated=false`, so the complete NXP denominator and % coverage **remain null**, not 0% or 100%.

Run locally:

```bash
python data/device-catalog/research/nxp_bulk_coverage_v1.py
python -m unittest discover -s data/device-catalog/research -p 'test_nxp_bulk_coverage_v1.py'
```

Once family acquisition jobs exist, point `--evidence-root` at a directory with `mcx.json`, `kinetis.json`, etc. All files are **research-only** and need an independent source-evidence review; accepting them does not mutate Production.

## Next gates before mass admission

1. **Gate 1: Official portfolio source map.** Audit actual NXP family leaves, S32K exclusion, publication/lifecycle semantics and duplicates; freeze source URLs and immutable evidence with explicit scope (no generic NXP-wide coverage KPI).
2. **Gate 2: Matrix acquisition.** Implement versioned, read-only GitHub Actions `workflow_dispatch` family/page runners with rendered NXP Package/Quality tables, bounded pages, source hashes, verified official counts where present, artifacts and independent source-level retries. Do not run unreviewed live scraping from arbitrary PR changes.
3. **Gate 3: Gap report.** On reconciled official exact Active sets compute `A-P`, `P∩A`, `P-A`, and lifecycle unknowns. Treat CMSIS/OpenOCD patterns as discovery hints, **never** manufacturer Active authority. If denominator cannot be independently proven, keep partial scope.
4. **Gate 4: Family metadata and bounded proposals.** Manufacturer ordering tables determine exact package, pins, flash, suffixes, lifecycle and revision. Opaque suffixes stay opaque. Require deterministic validators, historical byte preservation, source digest and explicit per-batch owner approval.
5. **Gate 5: Production promotion.** Separately update canonical CSV, manifest counts / Git blob and SHA-256 bindings, run Catalog/API/IC selector regressions and merge via normal gate. Backend mapping remains `no_mapping` unless independently proven by the actual pinned OpenOCD runtime. Real DUT/HIL never implied.

## Retained KL25 pilot

Existing official NXP KL2x research identified **12** Active KL25 ordering codes with `catalog_admission_ready=true`. These 12 are a suitable *first bounded family publication candidate*, but they do not establish NXP portfolio denominator; the current Production manifest still has only ST sources. Neither prior KL25 Software Executor evidence nor this bulk plan grants Production publication or physical SWD programming.


## Gate 1a — real NXP Official Product Page Pilot (separate live acquisition workflow)

The read-only matrix workflow `.github/workflows/device-catalog-nxp-official-pilot-acquire-v1.yml`
captures three **curated** official NXP product-page lifecycle tables, independently:

- `mcx-c04x` — MCX C04x, expected exact Active row `MCXC041VFK`.
- `mcx-n23x` — MCX N23x, expected exact row `MCXN236VPBT`. The NXP official table includes `Qualification` entries which must *not* be counted as Active.
- `kl25` — NXP KL2x Package/Quality page, restricted to `MKL25Z` exact codes and expected `MKL25Z128VLK4`.

The Playwright scraper captures rendered raw HTML before parsing. It takes the exact orderable part number from the **Material Declaration** cell immediately preceding the official **Status** cell, not from the **Part/Package** group label: e.g. an MCXC041VFK group can include MCXC041VFKR, and an MCXN236VDFT group can include MCXN236VDFR. It rejects contradictory or duplicate lifecycle states and uploads JSON + HTML as temporary GitHub Actions artifacts even on failure. The non-lifecycle Quality Information table is excluded by the absence of an adjacent official Status value. The product URLs are fixed in `nxp-official-pilot-products-v1.json` and cannot be supplied arbitrarily. **Every snapshot has `source_population_complete=false`**, since a bounded product page does not establish complete MCX/Kinetis/NXP manufacturer coverage. This pilot is an actual manufacturer acquisition probe, not a mass-portfolio denominator or a production admission.


## Gate 1b — Bounded official evidence Gap Reconciliation

After all three official product-page acquisitions pass, the workflow downloads each
source's raw rendered HTML and normalized row evidence. The offline
`nxp_official_pilot_reconcile_v1.py` re-hashes the raw HTML, checks the
fixed product-page allowlist, exact SKU and lifecycle integrity, checks live KL25's
exact 12 Active identities against the frozen manufacturer evidence, then produces
`bounded-pilot-gap.json` and observed Active / Qualification exact-MPN lists.
Cross-product lifecycle contradictions are hard errors.

**This report is bounded observed-source coverage, not whole-NXP coverage.**
`global_active_denominator` and `global_active_coverage` stay JSON `null`;
`observed_active_missing_from_production` is only the gap within these three
verified pages. Full family inventory and manufacturer category completeness
remain open research gates.

## Gate 1c — six portfolio lanes represented by live manufacturer product pages

The official read-only pilot matrix now includes fixed NXP Package/Quality
pages for `LPC55S6x`, `K32-L2`, `i.MX-RT1060` and `KW45` alongside
MCX C04x, MCX N23x and KL25. Thus all six **research acquisition lanes**
(MCX, Kinetis, LPC, K32, i.MX RT, wireless) have bounded current-surface
probes. This is *not* a manufacturer family-wide or portfolio-wide
enumeration; all seven remain `source_population_complete=false`.
Retain `Active`, `Qualification` and `No Longer Manufactured` as
different literal official lifecycle states. No unmapped NXP device gains
a Programming Profile merely by appearing in this report.

## Gate 1d — MCX A/C/E/N official-source batch

An additional **12 pinned official MCX product pages** were admitted into the
read-only research acquisition manifest after confirming the manufacturer's
Package/Quality source surface. Together with the original seven, the bounded
matrix now contains **19 product pages** across six broader research lanes.
The run is throttled to four concurrent product-page captures to reduce
unnecessary load on NXP and on Actions runners.

- MCX A: A13x/A14x/A15x, A17, A18, A25, A26, A34, A35, A36
- MCX C: C14x/C24x/C44x
- MCX E: E24, E31
- MCX N: N94/N54/N53/N52/N24
- Prior pinned pages: MCX C04x/N23x, KL25, LPC55S6x, K32 L2,
  i.MX RT1060, KW45.

These are individually corroborated product page leads, **not** manufacturer
total-family enumerations. Every official page must be captured successfully
and remain `source_population_complete=false`, with NXP-wide denominator
and percentage `null`. Cross-page repeated commercial identities are
deduplicated by exact identity and contradictory lifecycle blocks the gate.

## Gate 1e — manufacturer-verified MCX C/W follow-on pages

The live six-series MCX index audit completed with **21 observed product-page
leads** and **7 not represented in the original 19-page research pilot**.
These are observed navigation leads, not evidence of complete NXP inventory.

Four of the seven were checked against their official NXP Package/Quality
Environmental Information rows and pinned to exact *material-declaration*
ordering SKUs in the read-only matrix, now **23 bounded product pages**:

- MCX C15/C16 — `MCXC162VLF`
- MCX W23 — `MCXW236BIUKAR`
- MCX W71 — `MCXW716CMFTAR`
- MCX W72 — `MCXW727DMFTBR`

The remaining indexed pages `MCX-A5`, `MCX-L14`, and `MCX-L25` are
**discovered but not yet anchored to verified exact SKUs**. Do not fabricate
`must_include` sentinels for them. Reconciliation must continue to report
manufacturer-wide Active identity counts and coverage as `null`.

The LPC55S6x pilot sentinel was also corrected from the package/group label
`LPC55S69JEV98` to the observed orderable SKU `LPC55S69JEV98E`.
The former makes a valid live product acquisition fail when the scraper
correctly distinguishes group labels from ordering SKUs.
