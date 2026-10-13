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
