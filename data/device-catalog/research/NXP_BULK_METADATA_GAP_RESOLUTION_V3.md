# NXP 353 Active Exact ICPN — Manufacturer Metadata Gap Resolution v3

**2026-10-13. Research-only. No Production Catalog writes, target programming
permissions, HIL claims, or global NXP Active denominator.**

## Single-batch approach (same ST late-stage reconciliation mechanics)

Continuing merged #828, #832 and #835, preserve **one 353-exact-ICPN
candidate set** and the 8-shard evidence archives from [run 38337377867](https://github.com/physicslu/plasma/actions/runs/38337377867).
The job shards are transport/concurrency only; they do not create
individual Production admission transactions.

The #835 all-353 manufacturer HTML replay reached:
12 prior manufacturer-reviewed KL25, 201 full four-field manufacturer
/part observations requiring canonical review, 47 partial observations,
93 blocked /part observations.

### Recovery #1 — exact manufacturer LFBGA64 package contact evidence

Among 47 partial observations, exactly **11** LFBGA64 variants have
an original manufacturer `/part/<exact SKU>` HTML page whose package
description explicitly says **“64 bumps”**. The older parser accepted
only `pins`, `balls`, `terminals`, `leads`, not `bumps`.
The independent v3 gate requires:

- exact SKU in manufacturer document H1;
- originally locked HTML SHA-256 with no changed source bytes;
- `Package` section has exact `LFBGA64` name and **64 bumps**;
- no contradictory bump/ball number; no suffix-based inference;
- a frozen list of exactly 11 original partial SKUs.

Result conditional on v3 CI: *201 + 11 = 212 source-four-field
observations*, still `REVIEW_REQUIRED`; remaining 36 partial,
93 source blocked and 12 separate KL25 metadata-reviewed identities.
This increases evidence completeness, **not** Production-ready counts.

### Recovery #2 — eight KW45 exact SKU multi-valued Flash source cells

For **8 KW45B41Z** exact Active codes, the official NXP `/part/`
product parametric Flash (kB) field is `256, 512` or
`256, 1024` — *two memory regions*, not an exact single-scalar
Flash size for the commercial ordering code. The old ingestion
correctly blocked scalar conversion instead of guessing.

NXP's official [KW45 data sheet, Table 1 p.4](https://www.nxp.com/docs/en/data-sheet/KW45.pdf)
lists **each exact ordering code**. In the manufacturer's merged-cell
radio ordering table, `KW45B41Z5...` group gives application Flash
512 kB / RAM 128 kB; `KW45B41Z8...` group gives application Flash
1 MB / RAM 128 kB. This is a different hardware memory claim than the
radio-core 256 kB Flash disclosed elsewhere in the data sheet.

`nxp_kw45_exact_flash_datasheet_v3.py` first verifies the eight
blocked identities against the frozen #835 blocked reason map. Its
**PDF binary replay code and negative-tests are implemented**, but the
original live acquisition using the NXP global and NXP Japan official
PDF routes both returned **HTTP 404 from GitHub Actions** (despite
the manufacturer PDF being browser-visible). Therefore the v3 CI
currently runs `--offline-source-gap` and saves **eight specifically
identified *unqualified* Flash candidates**, plus source URL and
failed acquisition status, without falsely claiming a vendor PDF
SHA-256 or machine-verified memory row-span.

The original table was separately visually inspected on the NXP
official PDF (Rev 9, p.4). That alone is **not automated source
retention/replay**, so the eight remain in the canonical review queue
until original binary evidence can be acquired and its exact table
cells can be independently verified. No application/radio Flash
merging, invented address map or OpenOCD permission.

### Remaining source exceptions

The original **85 exact `/part/` HTTP non-200** cases remain NXP
**Active** ordering identities from the independently observed
official Package/Quality table. Some are tape/reel variant names or
legacy/alternate orderables that do not have independently
resolvable product pages. Their metadata stays **unknown** until
manufacturer datasheet/order-table exact-SKU metadata can be
substantiated; do **not** erase or mark them Obsolete.

Other remaining partial cases include **23 i.MX RT** source pages with
no on-chip Flash scalar and no ambient temperature field, plus
**5 MCX** source pages missing Flash and ambient, and **8 KW45**
source pages missing ambient. Do not assign a fake zero-kB internal
Flash or confuse junction-temperature limits with ambient operating
range. A separate memory architecture and algorithm applicability
review is needed for crossover parts before a Production Catalog
schema can safely represent them.

The `nxp_metadata_gap_queue_v3.py` generator permanently derives a
single **129 exact-SKU** exception CSV and fails if its checked-in
rows differ. The queue is divided into **85 official /part HTTP
non-200**, **8 KW45 flash multi-value needing PDF replay**,
**23 i.MX RT flash/ambient**, **5 MCX flash/ambient**,
and **8 KW45 ambient**. These are metadata-evidence routes, not
backend mappings or presumed datasheet equivalences.

## Admission boundaries

1. Read-only acquisition, original HTML/PDF evidence, exact matching,
   lifecycle and durable SHA evidence are research-scoped steps.
2. Complete-looking source fields do **not** establish canonical
   package/temperature/flash *semantics*, secure-boot behavior,
   physical viability or supported flash programming backend.
3. One future ST-style **large controlled Production proposal** will
   require a manufacturer-document-backed canonical manifest,
   frozen `Active - Production` exact set, negative tests, and
   explicit owner approval before any write.
4. The CI output of this PR is temporary (GitHub Actions retention).
   Permanently committed previous #835 per-SKU status map remains
   the pre-v3 baseline, and this v3 change records only *new
   evidence*, never silent reclassification of earlier observations.
