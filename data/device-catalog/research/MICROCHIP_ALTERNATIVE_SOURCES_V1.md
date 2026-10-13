# Microchip alternative source audit — 2026-10-13

Status: research discovery only. This note does not admit Production ICPNs.
The lists below are observations from retrieved official-site text or search-index
extracts, not an archived manufacturer API response. No original response-byte
SHA-256 is claimed.

## Source routes and observed access

| Source | Observed capability | Evidence boundary |
| --- | --- | --- |
| [Microchip MCP documentation](https://www.microchip.com/en-us/resources/model-context-protocol-server) | Documents a public, no-authentication Streamable HTTP service at https://api.microchip.com/mcp/resources with product identity, package, specification and document data. | Documentation read; initialization, tool discovery, pagination and exact-SKU lifecycle fields have not been validated. Direct network access to this host is unavailable in the current execution environment. A browser GET failure is not evidence of MCP service failure. |
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
