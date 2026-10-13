# NXP — 353 Exact Active ICPN bulk metadata qualification v2

Date: 2026-10-13. **Manufacturer-evidence review only: no Catalog
Production admission, no programming/HIL claims.**

## Original manufacturer acquisition (merged #832)

- 353 distinct exact Active ordering identities; Active set SHA-256
  `8d25ee58d833b69d9d6b6bc68bd20d11090c33c543e606507b95ce667267eb24`.
- 12 KL25 have independent existing datasheet/ref-manual metadata review.
- One 341-SKU remaining metadata acquisition, spread across eight **execution
  shards** (not eight admission PRs), source [GitHub Actions #38337377867](https://github.com/physicslu/plasma/actions/runs/38337377867).
- Original findings: **201** official part pages with all four requested
  fields; **47** source pages with missing fields; **93** blocked part pages.
- From retained raw `metadata-shard.json` files, precisely **85** blocked
  rows had non-200 responses from `www.nxp.com/part/<exact-SKU>`; the
  other **8** had Flash fields not matching the acquisition parser's numeric
  `Flash (kB)` contract. These are *parser/source statuses*, not proof
  that an exact commercial part is unsupported by the manufacturer.
- Among the 47 partial rows: 23 i.MX RT were missing flash/ambient,
  8 Wireless were missing ambient, 8 MCX and 3 K32 were missing explicit
  pin/ball count, 5 MCX were missing flash/ambient. Preserve unknowns.
- The manufacturer exact ordering identity was already established from
  a distinct official Package/Quality page, not the optional `/part/`
  metadata URL. A failed metadata page must not negate the official
  Active identity or fabricate a replacement ordering suffix.

## New controlled qualification

`nxp-bulk-353-metadata-evidence-lock-v2.json` pins **each of the eight
original metadata-shard JSON SHA-256s**, source artifact IDs, frozen Active
set hash, prior workflow and zero-production permission. Raw HTML for
all 248 successfully acquired official `/part/` pages is retained in the
corresponding 30-day artifact.

The `nxp_metadata_qualification_v2.py` gate independently parses the
**original rendered manufacturer HTML** and checks:

- exact commercial SKU equals an original manufacturer `h1`;
- original package text includes the same source package identifier,
  and pin/ball/lead count explicitly matches if recorded;
- claimed numerical Flash (kB), ambient temperature and optional
  junction temperature are independently located in matching official
  product specification cells;
- compressed raw HTML source matches the original source SHA-256 and
  the eight-shard identity/ordering/provenance contracts;
- all 353 exact Active identities are present, with no non-Active
  additions or fabricated whole-vendor denominator.

The gate outputs **one full 353-row evidence replay CSV**, a
**341-row exception/review queue** and machine-readable count/reason
report as temporary GitHub Actions artifacts.

Even for an HTML-replayed four-field row the admission state remains
`REVIEW_REQUIRED`: four observed fields are not a complete ST-style
canonical family-specific schema or device support qualification.
Manufacturer package nomenclature, flash geometry, temperature/ordering
grades, BootROM/flash profiles and family-specific option variants must
still be separately validated. The 85 non-200 and 8 unexpected Flash
format cases stay explicit rather than being silently converted.

## Constraints and approval boundary

- Research-only scope: 23 selected NXP product pages; no NXP-global
  Active denominator and no NXP-wide percentage.
- No changes to `data/device-catalog/production/`, the Web selector,
  target profiles, programmer code, PS, PL, or hardware.
- Raw manufacturer artifacts are ephemeral: they expire 2026-11-12.
  Any later Production transaction requires renewed/re-retained raw
  evidence, exact-set replay and separately approved bounded admission.
- **Only the eventual research PR merge requires owner approval now.**
  This gate is not sufficient authorization for 201, 213, 353 or any
  other count of Production-admitted NXP SKUs.

## Next ST-style large batch

Resolve 8 non-numeric Flash-field source cases with an explicit raw-value
parser that never guesses a size; separately re-evaluate 85 unavailable
exact `/part/` URLs against official manufacturer ordering/datasheet
sources. For i.MX RT do **not** substitute an external flash capacity for
missing on-chip Flash (kB). Complete family metadata and build **one
non-destructive dry-run Proposal** over whichever rows independently
pass canonical metadata review; request owner approval **before any
Production write**, not for each individual part.

## Permanent per-SKU review-state baseline

The `nxp-bulk-353-status-map-v2.json` companion provides a compact,
SHA-256-protected, **per-SKU index** (not only counts), keyed by the
position of each exact ordering identity in the sorted and immutable
`nxp-active-353-bulk-candidates-v1.csv` list. It permanently retains
every status (K/C/P/B) and every blocked root cause (H/F).

`nxp_metadata_status_index_v2.py` reconstructs the complete
`nxp-353-review-status-index.csv` **without any live website or
expiring Actions artifact**. It rejects changes to the 353 identity
set, status SHA-256, blocked reason SHA-256, source-pair consistency
or unauthorized production/vendor-coverage claims.

The original manufacturer HTML still remains necessary for
**canonical metadata admission**. The permanent status map is an
auditable triage index, **not a replacement for raw source proof**.
