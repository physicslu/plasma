# NXP Manufacturer Device — Discovery / Metadata / Production Bulk v5

**Scope restricted to three workstreams:**
1. exact manufacturer ICPN discovery and **Active** lifecycle evidence;
2. official manufacturer **Device** metadata;
3. bounded Production Catalog identity/Device admission.

Programming Profile, OpenOCD, executable backends, FPGA/PPU and physical HIL
are **not** part of this workstream. The canonical `no_mapping` state is
deliberate and is not a programming failure.

## Manufacturer evidence

- Existing **353** observed Active Exact ICPNs are from **23 specified NXP
  product pages**, **not** the full worldwide NXP Active denominator.
- Exactly **12 KL25** were already published to Production by PR #839.
- **212** more have replay-verified manufacturer per-exact-SKU part-page
  Package, contact count, Flash (kB) and Ambient Temperature, including
  eleven LFBGA64 SKUs with the manufacturer's explicit `64 bumps`.
- **129** remain blocked/partial, and are *not* included.
- The source is the manufacturer's **original rendered HTML**, independently
  checked by exact SKU H1 + SHA-256 from eight frozen
  run `38337377867` archive shards.

## Manufacturer Device schema

The exact-SKU Device ledger collects:
`ICPN`, `Base Device`, `Package`, `Pin Count`, `Flash`, `RAM`,
`Operating VDD`, `I/O Supply`, `VDDA`, `Operating Temperature`.

Only values explicitly present in the exact manufacturer's page may be
populated. NXP `SRAM (kB)` and `Supply Voltage [Min to Max] (V)` are
extracted from original HTML on a per-SKU basis. No RAM or voltage is
calculated from family product marketing maximums. **I/O Supply, VDDA
stay blank / not individually sourced** until official device-specific
data are available; missing is not 0 or automatically equal to VDD.

Original source does not necessarily offer a manufacturer-approved
Base Device crosswalk. Until it does, Layer-1 import chooses a
**single-SKU singleton `base_device=ICPN`**, explicitly documented
as a fallback, **not** a claim of official Base Device equivalence.
No suffix is stripped, no part codes are normalized into aliases.

## Layer-1 Catalog only

- Every new canonical SKU is exact, Active, manufacturer evidence-locked.
- Metadata fields from original source have non-ambiguous exact values.
- `mapping_status=no_mapping`, empty `openocd_target_config`,
  empty `existing_identifier`, no Programming Profile.
- Manufacturer Device *full* profile is explicitly incomplete when
  RAM/I/O/VDDA/supply or true base grouping are unverified.
- Production membership is a **Catalog identity/Device Layer-1**
  decision; the UI must not imply the IC is electrically programmable.

## QA and owner control

All 353 must reconcile:
`12 previous Production KL25 + 212 manufacturer-source-ready candidates +
129 blocked/partial = 353`. Never admit any blocked/lifecycle-inactive
ICPN, or infer a pin/flash/temp field by suffix.
Production manifest updates require **one large Draft PR and one explicit
owner merge approval**, after full repository CI. No other gate approvals.

The initial workflow emits **review artifacts only**. Only after all
212 exact rows are regenerated from original official SHA-locked HTML
should the corresponding canonical source be staged in the PR branch.
