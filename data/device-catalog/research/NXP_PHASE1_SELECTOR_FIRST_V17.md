# NXP ADR-0002 Phase 1 — Selector-first official 224 ICPN source audit v17

**Scope:** Approved Phase 1 IC Information only. Proposed PR from merged `main`.
No Production admission change, no default Catalog/Console API/UI, no Job/Batch,
no Programming Guide / Flash Driver investigation, no Socket/PPU/HIL.

## Pilot results, with separate denominators

- **224** already-admitted NXP exact manufacturer ICPNs are represented in
  an exhaustive **internal identity audit table**, *not* 224 completed
  remote website checks.
- From individually observable, exact official NXP SKU rows in THIS
  bounded research pass: **13 NXP Buy/Parametrics search-indexed row
  observations** (MCX C151/161/162 9; MCX W71 4) plus **26 original
  NXP Fact Sheet exact-part table rows** (MCX C04/C14/C24/C44 18,
  MCX E24 8).
- **185** remaining admitted exact ICPNs were NOT exhaustively investigated,
  so `NO_EXACT_ROW_EVIDENCE_IN_V17` is **not** an NXP catalog absence.
- No XLS, live dynamic-table API payload or original HTML / PDF binary
  was acquired or durably archived. Therefore **0 verified XLS-export
  source rows**. All provenance is official URL, document/title,
  table/page and immutable project-side transcription; indexed HTML
  entries are `PARTIAL` rather than falsely `VERIFIED`.

## Field policy

- 26 exact Fact Sheet table rows yield **SRAM = VERIFIED** because
  the original NXP official table was visually reviewed (but original
  PDF SHA256 is not asserted).
- 13 exact *indexed* Buy/Parametrics rows yield **SRAM = PARTIAL**
  because the interactive NXP table itself was not archived. The
  9 MCX C151/161/162 SKU-indexed `Supply Voltage 1.71–3.6 V`
  fields are `PARTIAL`, not fully independently replayed.
- NXP [MCXCFS Rev 0](https://www.nxp.com/docs/en/fact-sheet/MCXCFS.pdf)
  has **family-level** 1.71–3.6 V; it is propagated on the 18 exact
  fact-sheet rows as `PARTIAL`, distinct from exact SKU source.
- NXP [MCXE24FS Rev 1](https://www.nxp.com/docs/en/fact-sheet/MCXE24FS.pdf)
  describes a general 3–5 V architecture, **not** individual exact
  VDD min/max limits. Those eight VDD fields stay UNKNOWN.
  It also contains a contradictory **Cortex-M33 table header** versus
  narrative **Cortex-M4F**; do not import Core from that table.
- NXP [MCX W71 official Buy/Parametrics](https://www.nxp.com/products/MCX-W71?tab=Buy_Parametric_Tab)
  has 4 exact SRAM rows but not a qualified exact VDD column in the
  available indexed view; mode-dependent operating voltage is
  **not** silently mapped to a universal VDD.
- Individual I/O supply, VDDA and actual programming behavior remain
  outside this recovered source set; unchanged.

## 224 admitted-only metrics (v16 → v17)

| Field | Previous Verified / Partial / Unknown | v17 Verified / Partial / Unknown |
|---|---|---|
| RAM | 16 / 0 / 208 | **42 / 13 / 169** |
| Working VDD | 16 / 0 / 208 | **16 / 27 / 181** |

Research 277 remains unchanged. 501 identity rows are retained. The
apparent 224-row study is **a coverage gap ledger**, not a statement
that NXP official selector returned 224 exact parts.

## Deterministic files and CI

- `nxp-39-official-source-rows-v17.csv`: 39 exact-source observations
  including source class, original page/table, Flash cross-check, SRAM,
  conditional VDD field and explicit confidence limit.
- `nxp-224-parametric-source-audit-v17.csv`: full 224 internal identity
  evidence disposition, without changing their admission.
- `nxp-501-phase1-selector-first-v17.csv`: previous 501 info fields
  plus 39 new source-scoped SRAM values, 27 partially evidenced VDD
  ranges and provenance.
- `nxp-phase1-selector-coverage-v17.json` and lock
  `nxp-phase1-selector-source-lock-v17.json`, generator and tests.
- CI independently replays the locked v16 501 baseline and exact
  39 source-row Git blob, checks Flash identity equality, enforces
  no new admission / support / runtime / HIL and verifies audit
  coverage denominators.

## Next verified acquisition decision

To scale from 39 to 224, first establish a legitimate, stable NXP
exact-part Parametrics export/XLS retrieval process or access to
authenticated official source files. **Do not** assume public
product pages' JavaScript shells contain directly scrapeable values.
Only promote a field when actual exact manufacturer evidence can be
replayed; otherwise retain its existing state. Prioritize MCX A,
MCX N and remaining MCX E/Dynamic families separately.
