# IC Information — Catalog Level 1 identity/evidence contract

Status: **Catalog Level 1 identity baseline established; Programming Qualification work approved 2026-10-15.** Filename retains legacy `phase1` for compatibility. Device Registry / Programming Catalog runtime migration remains separate.

## Right-hand IC details: independent Catalog Level ownership

| Section | Catalog Level | Purpose | Is it currently in scope? |
| --- | --- | --- | --- |
| 01 IC Information | Level 1 — `IDENTIFIED` | Original manufacturer IC identity / specifications, exact-ICPN evidence, known/unknown per field | BASELINE / BACKFILL ONLY |
| 02 Programming | Level 2 — `PROGRAMMABLE` | Provider qualification; `SUPPORTED` programming evidence for the exact ICPN | YES — CURRENT |
| 03 PLASMA Compatibility | Level 3 — `PLASMA_VERIFIED` | Versioned PPU/Site/Socket/Adapter/FPGA/PS + voltage/pin and HIL evidence | NO |

## Catalog Level 1 canonical information fields

- `manufacturer`, `icpn` (exact ordering code), `base_device`;
- `package`, `pin_count`, `flash`, `ram`, `vdd`, `io_supply`, `vdda`, `temperature`;
- optional `core_architecture`, `core_model` only where attributable to the manufacturer device or its documented family.
- Each property has `value`, `unit` (where applicable), `state` (`VERIFIED`, `PARTIAL`, `UNKNOWN`, `CONFLICT`), the *exact vs family* source-scope and a manufacturer source locator and available hash/document revision.
- Original text is preserved for voltage intervals and temperature grades rather than converting incomplete ranges into invented typical operating values. Preserve a real numeric zero if the source explicitly says zero; an absent number is **not** zero.
- Exact commercial identity acceptance and metadata completeness are separate questions. The Research Inventory may contain a candidate exact order string with missing manufacturer evidence without admission to the internal Production Identity Store.

## Acceptance gates

1. Rebuild a deterministic manufacturer-data ledger from pinned original inputs, without reading Programming or PLASMA Compatibility records as metadata sources.
2. Count `VERIFIED/PARTIAL/UNKNOWN/CONFLICT` for every attribute, with independent admitted/candidate denominators; count unresolved identity separately.
3. Record original manufacturer evidence SHA or source ref when it exists. A `PARTIAL` observation does not qualify a software profile; a missing attribute does not create an unsupported software decision.
4. No `openocd_software_support=SUPPORTED`, `Hardware Ready`, public selectable `Catalog`, Job/Batch, Production admission mutation or physical PASS is derived by Catalog Level 1 identity evidence.
5. Programming Qualification work was approved on 2026-10-15. Level 1 evidence may be backfilled while reviewing the same official manufacturer documents, but `SUPPORTED` qualification is what derives Level 2 `PROGRAMMABLE`. Level 3 separately validates concrete Site/Adapter/Socket/PPU/FPGA/PS configurations.

## Catalog surface distinction

There are three different concepts: **Level 1 identity**, **Level 2 programming eligibility**, and **IC Information field completeness**. An Exact ICPN with Level 1 `IDENTIFIED` belongs to the Canonical Device Registry even when some information fields remain `UNKNOWN / PARTIAL / CONFLICT`; `INFORMATION_COMPLETE` does not change the Catalog Level.

Only a `ProgrammingQualification.state == SUPPORTED` derives Level 2 `PROGRAMMABLE` and Programming Catalog / general IC Selector membership. Level 1-only ICPNs stay available to Engineering through the Device Registry. Level 3 `PLASMA_VERIFIED` is an additive verified-configuration status. Selector membership never grants Job/Batch execution.

## Examples outside Catalog Level 1 identity

- Does the pinned OpenOCD `lpc2000` ROM IAP algorithm program LPC845 successfully?
- Is the target Part ID present, and does readback verify?
- Can a PPU Site safely supply VDD and program a particular Socket?
- Is the machine configuration `READY` or HIL `PASSED`?

These belong to Programming Qualification / Catalog Level 2 or PLASMA Compatibility / Catalog Level 3, not missing IC Information columns.
