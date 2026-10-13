# Microchip alternative source audit — 2026-10-13

Status: research discovery only. This note does not admit Production ICPNs.
The lists below are observations from retrieved official-site text or search-index
extracts, not an archived manufacturer API response. No original response-byte
SHA-256 is claimed.

## Source routes and observed access

| Source | Observed capability | Evidence boundary |
| --- | --- | --- |
| [Microchip MCP documentation](https://www.microchip.com/en-us/resources/model-context-protocol-server) | Documents a public, no-authentication Streamable HTTP service at https://api.microchip.com/mcp/resources with product identity, package, specification and document data. | On 2026-10-13 the execution environment successfully performed initialize (HTTP 200), initialized (202), tools/list (200, six tools), and search_products for PIC10F202 at limit 2 / offset 0 (200). The query reported eight matches and returned two rows with explicit lifecycleStatus=Active. A later full-capture attempt was cancelled by the execution tool before a network approval decision and captured no response bytes. Full pagination remains unvalidated. A browser GET failure is not evidence of MCP service failure. |
| [Parametric Search guide](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/MarketCommunication/Promotions/Parametric-Search-User-Guide-00004852.pdf) | DS00004852A documents XLSX Download Chart / All Data, with all products and columns in the selected chart. | No workbook captured. Chart scope must be recorded; an export does not by itself prove manufacturer-wide coverage or full ordering suffixes. |
| [Official packs repository](https://packs.download.microchip.com/) | Lists versioned Device Family Packs and supported device names; the PIC10-12Fxxx group is readable. | Tool-support names are discovery candidates, not commercial order codes or lifecycle authority. Pack archives have not been downloaded or hashed. |
| [PCN/EOL portal](https://www.microchip.com/en-us/support/product-change-notification) and [CPN FAQ](https://ww1.microchip.com/downloads/en/Market_Communication/PCN%20FAQ_revision.pdf) | Public notification access; affected CPN attachments identify ordering part numbers, sometimes in spreadsheet form. | Check revisions, cancellations and effective dates. Absence of an EOL match does not prove Active status. |
| [PIC10F206 product page](https://www.microchip.com/en-us/product/pic10f206) | A search-index extraction exposed ten Catalog Parts identifiers and package columns. | A subsequent direct page retrieval omitted the catalog table. Treat these as indexed candidates awaiting a stable source capture, not a complete live population. |

The [Data Exchange Portal](https://www.microchip.com/designresources/partnerDataExchange/data-feeds)
also advertises product feeds. A usable product-feed download has not been
obtained; its existence is not a completed acquisition.

## Bounded DFP discovery list

Observed pack: PIC10-12Fxxx_DFP, version 1.10.193, release date 2026-09-02.
The official repository lists 27 supported device names for this pack:

```text
PIC10F200
PIC10F202
PIC10F204
PIC10F206
PIC10F220
PIC10F222
PIC10F320
PIC10F322
PIC10LF320
PIC10LF322
PIC12F508
PIC12F509
PIC12F510
PIC12F519
PIC12F529T39A
PIC12F529T48A
PIC12F609
PIC12F615
PIC12F617
PIC12F629
PIC12F635
PIC12F675
PIC12F683
PIC12F752
PIC12HV609
PIC12HV615
PIC12HV752
```

These are 27 distinct observed discovery names, not 27 admitted ICPNs. The
count reconciles only this displayed pack list. It is not a global PIC/AVR or
Microchip denominator.

## Indexed exact-ordering candidates: PIC10F206

The following ten distinct strings appeared in the official product page's
search-index Catalog Parts table:

```text
PIC10F206T-I/MC
PIC10F206-E/P
PIC10F206-I/P
PIC10F206T-I/OTGVAO
PIC10F206T-I/OT
PIC10F206-E/MC
PIC10F206-I/MC
PIC10F206T-E/OT
PIC10F206-E/OT
PIC10F206-I/OT
```

Preserve each full string, including T and GVAO; do not strip suffixes or
generate missing variants from naming patterns. No per-SKU lifecycle status
was established. Stock and ordering availability are not lifecycle evidence.
These candidates must not enter the existing complete-snapshot validator as
manufacturer-verified records.

## Next acquisition steps

1. Retrieve a stable DFP/PDSC or official chart export, retain original bytes,
   timestamp and hash, and reconcile candidate names within the captured scope.
2. In an environment with authorized access to the official MCP host, perform
   initialization and tool discovery. Inspect actual schemas before issuing a
   fixed read-only product query; do not guess tool names or assume bulk listing.
3. Capture exact catalog-part tables for a bounded base-device set. A missing
   dynamic table is an incomplete capture, not an empty product population.
4. Establish SKU-level lifecycle evidence from explicit manufacturer fields
   and applicable PCN/EOL records, preserving unknowns and conflicts.
5. Only then produce a bounded admission proposal. Manufacturer-wide
   completeness and Production publication remain separate gates.

This audit provides a public-source continuation path; it does not require
the owner to supply credentials merely to continue source discovery.

## MCP probe continuation

`microchip_mcp_probe_v1.py` implements the observed MCP schema with a fixed
PIC10F202 query. It initializes the session, discovers the tool, fetches pages
of two (at most 60 rows), and compares the identity/lifecycle set against a
limit-60 response. Raw response bytes, timestamps, request arguments and SHA-256
digests are retained. `--replay` validates an existing capture offline.

The earlier successful query returned `PIC10F202T-I/MC` and `PIC10F202-I/MC`,
both with raw `lifecycleStatus=Active`; its reported total was eight. That
interactive result was not archived by this probe and is not a replayable
fixture. Do not reconstruct original bytes from the displayed text.

The new full-capture attempt produced no responses because the execution tool
reported: `network approval was cancelled before a decision was returned`.
This is an execution/access limitation for that attempt, not a vendor failure,
and does not negate the prior successful MCP calls. No full-capture success,
complete family population, or Production admission is claimed.

Run from the repository root with a new output directory:

```bash
python data/device-catalog/research/microchip_mcp_probe_v1.py --output-dir /tmp/microchip-mcp-capture
python data/device-catalog/research/microchip_mcp_probe_v1.py --output-dir /tmp/microchip-mcp-capture --replay
python -m unittest discover -s data/device-catalog/research -p 'test_microchip_mcp_probe_v1.py' -v
```

Keep the PR Draft while the full capture and family inventory remain open.

## Bounded PIC10/PIC12 MCP batch implementation (research only)

The 27 device names observed in the PIC10-12Fxxx Device Family Pack are frozen
as **candidate search terms**, not proven orderable-SKU populations, in
`microchip-pic10-pic12-mcp-batch-seeds-v1.json`. The file explicitly retains
`population_boundary_validated=false` and `global_active_denominator=null`.
It is a transcribed discovery list; source pack archive bytes have not yet
been captured or independently hashed.

`microchip_mcp_probe_v1.py` now accepts a validated alphanumeric `--query`
(default `PIC10F202`) while preserving the two-row pagination, 60-row hard
bound, cross-page identity/lifecycle comparison, original response bytes and
SHA-256 evidence. Its offline replay checks the complete archived JSON-RPC
handshake and exact request order, not just the product-page totals.

`microchip_mcp_batch_v1.py` runs the 27 queries sequentially (or a bounded
prefix of 3/10 for transport canaries). Every device has its own
`manifest.json`, captured responses and `summary.json` where successful.
The batch writes `batch-summary.json` even when some queries fail; failures
are explicit and the command exits nonzero unless every selected bounded
search reconciles. It never writes a Production catalog.

Example, when a permitted network execution environment is available:

```bash
python data/device-catalog/research/microchip_mcp_batch_v1.py \
  --output-dir /tmp/microchip-mcp-batch --max-queries 27
python data/device-catalog/research/microchip_mcp_batch_v1.py \
  --output-dir /tmp/microchip-mcp-batch --max-queries 27 --replay
```

A separate workflow `.github/workflows/device-catalog-microchip-mcp-batch-v1.yml`
provides manual, read-only 3/10/27-query capture with short-lived raw evidence
artifacts once that workflow is available on the repository's default branch.
The research CI executes offline contract tests automatically; those passing
tests must not be described as a successful live capture. A temporary
3-query PR canary may validate Runner connectivity without importing its
observations into Production.

**Crucial limitation:** `search_products` is text search, not a proven
manufacturer-complete enumeration API. Even successful reconciliation of all
27 queries only confirms internal consistency of these bounded search
responses; it cannot establish exhaustive suffix coverage, historical/EOL
coverage, or the Microchip-wide Active denominator. Preserve unknown and
conflicting lifecycle values. Review exported manufacturer charts/feeds and
original PCN/EOL attachments before promoting any such claim.

### GitHub Runner live MCP canary — 2026-10-13

A three-device, read-only PR Runner probe finished successfully:
[GitHub Actions run 38337033289](https://github.com/physicslu/plasma/actions/runs/38337033289)
and [raw-response artifact 11784924015](https://github.com/physicslu/plasma/actions/runs/38337033289/artifacts/11784924015).
The artifact is a 23,551-byte ZIP, originally configured with 7-day retention,
containing 34 files including original MCP response bytes, per-response hashes,
and per-device manifests/reconciliation summaries.

| Candidate base-device query | MCP returned distinct ordering candidates | Bounded reconciliation |
| --- | ---: | --- |
| PIC10F200 | 11 | pass |
| PIC10F202 | 8 | pass |
| PIC10F204 | 9 | pass |

All three query results passed the strict two-row pagination and 60-row
identity/lifecycle comparison. Their summed **28 observed hits** are not a
verified manufacturer-complete active SKU set or Production admission list.
This also confirms GitHub Runner connectivity; the separate assistant-local
shell container did not resolve `api.microchip.com`.

The batch driver supports at most **two independent read-only MCP sessions**
(`--workers 2`) for larger captures. Each session stores its own response
bytes and manifest; the manifest order is the frozen DFP query order. The
27-query source-observation run must still be independently audited for
per-query failures, raw lifecycle values, chart/export cross-checks and
false-negative search behavior before coverage claims.

### Full PIC10/PIC12 DFP 27-query MCP results (2026-10-13)

Run #1 ([source artifact 11785323931](https://github.com/physicslu/plasma/actions/runs/38337429249/artifacts/11785323931))
reconciled 20/27 base-device searches under an overly restrictive
`basePartNumber == searchTerm` requirement. Its 20 passing queries contained
327 raw search results in total. Six other searches returned orderable part
numbers whose manufacturer `basePartNumber` was a related family, or contained
fuzzy matches; the seventh search, `PIC12F529T48A`, returned
`success=false` with `error=NOT_FOUND`. Neither mismatch nor absence means
that the corresponding commercial MCU is obsolete.

The probe now validates **every** raw result across page sizes 2 and 60,
but counts a query's exact-SKU candidates using a delimiter-aware part-number
prefix (commercial order strings such as `PIC12HV615-E/MF` remain attributed
to `PIC12HV615` even when raw basePartNumber is `PIC12F615`).
Every fuzzy foreign part is archived and counted separately. Overlap
reconciliation uses full ordering part numbers, not vendor base aliases.

Run #2 ([source artifact 11786145395](https://github.com/physicslu/plasma/actions/runs/38338256516/artifacts/11786145395))
completed 26/27 bounded queries and archived 366 files, with 397 raw hits,
50 foreign-device fuzzy hits, 347 exact-prefix ordering hits and 48
vendor-base aliases among those target hits. The 347 exact-prefix strings
were **all distinct across the 26 successful queries** in an independent
offline cross-query check of each `summary.json` in the captured ZIP.
The remaining `PIC12F529T48A` returned `NOT_FOUND` again.
This is a scoped empirical search result, not a full family enumeration,
manufacturer Active SKU denominator, or Production publication authorization.

A separately tested `microchip_mcp_evidence_ledger_v1.py` replays each
complete original-byte MCP transcript, then emits source-linked exact-SKU
research observations (original raw lifecycle and SHA-256 for each source
response, query, device identity and observed provenance). Incomplete or
tampered queries are excluded. That ledger is **research-only** and does not
write `data/device-catalog/production/`. A reproducible complete set still
depends on independent manufacturer source/export coverage and lifecycle
scope review.

**Outstanding:** Recover product evidence for `PIC12F529T48A` via
manufacturer-specific document/product lookup; do not fabricate its SKU list.
Expand frozen Device Family Pack discovery inventory beyond this single
27-device pack (there are separate PIC16/PIC18, AVR, dsPIC, PIC24, PIC32,
SAM and wireless packs) while filtering non-MCU, module and MPU entries.
Find an independent official orderable-product chart/feed to validate that
MCP text search returns all relevant commercial suffixes; recheck raw
Lifecycle per commercial SKU with PCN/EOL evidence.

### PIC12F529T48A reconciliation and replayable ledger evidence

The official [PIC12F529T48A product page](https://www.microchip.com/en-us/product/pic12f529t48a),
inspected on 2026-10-13, displays **"Status: End of Life"**. Thus the device
is a manufacturer-documented historical part, not an invented name or proof
of absence. Microchip's current public MCP `search_products` nevertheless
returned `success=false` with `error=NOT_FOUND` for this exact base query
on two separate 27-query runs. Its DFP supported-device presence documents
tool support, not commercial-ordering availability or active lifecycle.
The current product-page status is a **device-level EOL observation**, not
SKU-by-SKU EOL evidence; no ordering-code set is fabricated from naming rules.

A real offline ledger replay from
[run 38338627747](https://github.com/physicslu/plasma/actions/runs/38338627747)
produced [artifact 11786520772](https://github.com/physicslu/plasma/actions/runs/38338627747/artifacts/11786520772):
26/27 source queries independently replayed from captured original HTTP
bytes, yielding **347 distinct exact commercial-ordering candidates**, each
with the source query, original raw `lifecycleStatus`, raw response file
and SHA-256. All 347 observed raw statuses in this bounded sample were
`Active`. **This does not certify a complete Active denominator**; the
one EOL device's missing MCP results are a concrete example of why a text
search cannot be an exhaustive source.

The ledger step intentionally exits nonzero for the incomplete 27th query,
while still emitting the 347 source-linked research records with
`production_write_authorized=false`,
`manufacturer_population_complete=false`, and
`global_active_denominator=null`. No Production admission or runtime
programmer support is inferred. Resolve the missing historical ordering
parts from official PCN/EOL and manufacturer product tables, then scale
family discovery across the other DFPs.
