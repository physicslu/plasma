# Microchip official Product Data API — ADR-0002 Phase 1 original-byte pilot

**Status:** bounded, Research-only acquisition implementation; no Production or exact-ICPN admission.

## Manufacturer documentation and choice of source

The [Microchip Product Data API official user guide](https://www.microchip.com/designresources/PartnerDataExchange/ProductAPI-user-guide.html) documents a GET endpoint:

    https://www.microchip.com/designresources/product-catalog/api/productInfo?part=ATSAMD21G18A&pagesize=20&pagenumber=1

The guide describes structured manufacturer product fields including \`part_number\`, \`base_part_number\`, \`package_type\`, \`pin_count\`, \`datasheet_url\`, \`parametric_data_url\` and raw lifecycle data. It does **not** prove that the endpoint is reachable in all environments, or that search is a complete ordering-SKU census.

This is a valuable **independent exact-order-code source** to cross-check the existing official Microchip MCP \`search_products\` evidence. Both the Product Data API and MCP may use shared upstream manufacturer systems; agreement is not fully independent physical validation. The [Parametric Search chart XLSX importer](MICROCHIP_PHASE1_CHART_IMPORT_V1.md) remains a distinct manufacturer-family parameter source. No undocumented chart export endpoint or HTML 403 workaround is introduced.

## Implementation

\`microchip_phase1_product_api_v1.py\` uses Python stdlib \`urllib\` and a fixed allowlisted official HTTPS endpoint. A bounded **single base-device** query (\`ATSAMD21G18A\` by default) runs both 20-row and 60-row pagination; original JSON response bytes, exact requests, time, byte count and SHA-256 are retained in an immutable output directory. Offline replay independently validates each page's response metadata, identity, SHA-256, total count, complete pagination, and cross-pagination equality after excluding page-local array offsets.

Original \`part_number\` records are cross-referenced by complete, case-preserving commercial ordering string. The manufacturer-reported \`base_part_number\` is **not inferred by string trimming**. Manufacturer \`package_type\` and \`pin_count\` are compared with the two existing Research-only \`ATSAMD21G18A-MU / -MF\` pilot values, explicitly reporting \`AGREE / CONFLICT / UNKNOWN / NOT_OBSERVED\`. No existing Phase 1 pilot data is overwritten or promoted automatically. A match is additional manufacturer evidence, **not** internal \`ADMITTED\` and **not** OpenOCD \`SUPPORTED\`. All other returned exact-prefix orderable strings are Research candidates until reviewed.

The capture is bounded at **120 source results**. Zero or excessive results, changing pagination totals, duplicate identity, corrupted original SHA-256, non-JSON response, unexpected manufacturer, invalid pins, off-domain redirect and discordant independent pagination **fail closed**. Raw \`lifecycle_status\` is retained without treating it as a Product Catalog admission or a claim of Active lifecycle.

### CLI

Capture original bytes (a network-enabled execution environment is required):

\`\`\`bash
python data/device-catalog/research/microchip_phase1_product_api_v1.py \
  --query ATSAMD21G18A \
  --capture /tmp/microchip-phase1-api-original \
  --report /tmp/microchip-phase1-api-research.json
\`\`\`

Independently replay **the same** source bytes:

\`\`\`bash
python data/device-catalog/research/microchip_phase1_product_api_v1.py \
  --query ATSAMD21G18A \
  --replay /tmp/microchip-phase1-api-original
\`\`\`

Offline synthetic tests (fixtures are **not** manufacturer evidence):

\`\`\`bash
python -m unittest discover -s data/device-catalog/research \
  -p 'test_microchip_phase1_product_api_v1.py' -v
\`\`\`

The dedicated PR CI job executes offline tests and a **separate bounded live API canary**; the canary is \`continue-on-error\` because access restrictions must not fabricate a live-capture PASS or prevent landing a correct offline tool. Inspect the **live step's own outcome and archived manifest** to determine if original manufacturer evidence was acquired; generic workflow success is not enough. GitHub Actions source artifacts expire after **90 days** and therefore require a durable, separately verified archive before being used as permanent evidence.

### Explicit remaining gates

1. Confirm the live API endpoint responds and preserve original successful response bytes (or report \`SOURCE_NOT_AVAILABLE\`, not zero availability).
2. Independently compare exact code/Base Device/Package/Pin Count with separately archived original MCP responses. The new API's \`parametric_data_url\` is a **reference link**, not automatically validated Flash/RAM/VDD evidence.
3. Acquire one official Parametric Search XLSX to verify **actual** chart headings; source-lock it and compare the manufacturer **Base Device** rows with exact API/MCP identity links. The current XLSX CI uses synthetic fixtures only.
4. Bind per-ICPN family specifications using versioned datasheets and exact ordering applicability; keep \`PARTIAL / UNKNOWN / CONFLICT\` when evidence is incomplete. Internal identity-admission decisions require a separate owner gate.
5. Do not change Production, public Catalog/API/UI, OpenOCD Programming (Phase 2), PPU/Socket/HIL (Phase 3), Job/Batch, FPGA or runtime gating.

No worldwide Product API or MCP inventory completeness denominator is asserted. Prior 24,051 candidate ICPNs remain Research inventory; existing source-locked OpenOCD P0 → P1 → P2 prioritization is unchanged.
