# NXP — one 353-Active Exact ICPN bulk preflight, ST-style

**2026-10-13 | research only, no Production publication and no target access.**

## Transaction boundary

The owner requested the **ST late-stage bulk approach**, not a large number
of microscopic family PRs. Therefore this work treats all **353** observed
official NXP Active exact orderable identifiers as **one controlled batch**,
without promoting them to Production prematurely.

Input evidence is the previously merged #828 snapshot:
`nxp-official-bounded-snapshot-2026-10-13-v1.json`.

- 23 pinned manufacturer pages across MCX, KL25, LPC55S6x, K32-L2,
  i.MX RT1060 and KW45, not an exhaustive NXP vendor portfolio.
- Official observed **368 exact SKU identities**: **353 Active**,
  **2 Qualification**, **12 NRND**, **1 No Longer Manufactured**.
- Frozen Active exact-set digest
  `8d25ee58d833b69d9d6b6bc68bd20d11090c33c543e606507b95ce667267eb24`.
- At this prestate the NXP Production manifest has **0** NXP sources:
  `A - P = 353`; `P ∩ A = 0`; `P - A = 0`.
- Verified, manufacturer-document-backed metadata: **12 KL25 exact SKUs**.
  Remaining **341 exact Active identifiers** require independently sourced
  package/pins/flash/temperature/variant metadata.
- NXP global Active denominator and vendor coverage remain `null`; none
  of these quantities can be extrapolated from 23 selected pages.

## One batch pipeline

`nxp_bulk_admission_matrix_v1.py` validates **all 353 together** against
the immutable Active SHA-256, non-Active exclusions, source-page count,
KL25 source CSV, current Production prestate and explicit read-only policy.

The frozen `nxp-active-353-bulk-candidates-v1.csv` is a complete
**identity-level research batch**. Its evidence level
`frozen_official_exact_set_only` does **not** pretend per-row raw
manufacturer DOM evidence is persisted in this CSV. Missing metadata fields
are genuinely empty; no suffix decoding or backend compatibility is guessed.

The live GitHub Actions source matrix captures 23 official pages in parallel,
independently checks their DOM SHA-256 and 368 exact lifecycle partition, then
performs a **single cross-page 353-row preflight** using real manufacturer
`acquisition.json` row provenance. It uploads:

1. `nxp-active-353-bulk-candidates.csv` — all 353 identities, each with its
   official page URLs, per-row SHA-256, original DOM SHA-256; KL25 metadata
   only where independently validated.
2. `nxp-active-metadata-341-gap.csv` — the **341** rows still lacking
   manufacturer metadata, as one actionable enrichment queue.
3. `nxp-excluded-nonactive-15.csv` — complete Qualification, NRND and
   No Longer Manufactured exclusions.
4. `nxp-bulk-353-admission-preflight.json` — exact-set and readiness
   reconciliation, no guessed NXP-wide denominator.

CI must fail closed for source drift, duplicate/cross-page lifecycle
conflicts, untrusted manufacturer source links, missing verified KL25
metadata, 353-set SHA mismatch, missing row provenance, or any unexpectedly
existing NXP Production source.

## ST analogy and important distinction

The ST eStore gate supplied independent **whole-portfolio** Active facet
counts and complete category page enumeration. These NXP pages still do
**not** establish an exhaustive NXP-wide population. This PR reproduces
the **exact-set/transaction mechanics**, not the ST denominator claim.

Do not falsely count all 353 as `catalog_admission_ready`. The 12 KL25
identities have separate metadata evidence; other 341 require manufacturer
datasheets and official ordering-code mapping. Cross-family OpenOCD target
profiles, physical programming, security mutation and eight-Site runtime
support are different qualification dimensions.

## Next gate / explicit owner approval

Continue large-scale **manufacturer metadata enrichment** for the 341-item
queue; produce one reviewed batch manifest with per-SKU metadata source,
not 341 one-off PRs. If all 353 become metadata-complete, prepare one
bounded dry-run Catalog Production publication transaction with exactly
the expected canonical sources and SHA-256 / Git blob checks.

**Owner approval is required immediately before an actual Production
write or this PR's merge.** Research-only preparation is not such a write.
