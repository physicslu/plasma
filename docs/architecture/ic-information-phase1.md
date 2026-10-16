# IC Information — Catalog Level 0 identity/evidence contract

Status: **Catalog Level 0 identity baseline established; Programming Qualification work approved 2026-10-15.** Historical filename retains `phase1` only for path stability; active schema/API fields do not retain Phase naming. Research Registry / Programming Catalog runtime migration remains separate.

## Right-hand IC details: independent Catalog Level ownership

| Section | Catalog Level | Purpose | Is it currently in scope? |
| --- | --- | --- | --- |
| 01 IC Information | Level 0 — `DISCOVERED` | Original manufacturer exact-ICPN identity / specifications, known/unknown per field | BASELINE / BACKFILL ONLY |
| 02 Programming Research | Level 1 — `PROGRAMMING_CANDIDATE` | Source-backed Provider/target/driver/algorithm route worth qualifying | YES — CURRENT |
| 02 Programming | Level 2 — `PROGRAMMABLE` | `ProgrammingQualification.state == SUPPORTED` for the exact ICPN | YES — CURRENT |
| 03 PLASMA Compatibility | Level 3 — `PLASMA_VERIFIED` | Versioned PPU/Site/Socket/Adapter/FPGA/PS + voltage/pin and HIL evidence | NO |

## Catalog Level 0 canonical information fields

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
4. No `openocd_software_support=SUPPORTED`, `Hardware Ready`, public selectable `Catalog`, Job/Batch, Production admission mutation or physical PASS is derived by Catalog Level 0 identity evidence.
5. Identity evidence may be backfilled independently. A source-backed programming route promotes Level 0 to Level 1 `PROGRAMMING_CANDIDATE`; only `SUPPORTED` Programming Qualification promotes Level 1 to Level 2 `PROGRAMMABLE`. Level 3 separately validates concrete Site/Adapter/Socket/PPU/FPGA/PS configurations.

## Catalog surface distinction

There are four different concerns: **Level 0 exact identity**, **Level 1 programming relevance**, **Level 2 programming eligibility**, and **IC Information field completeness**. An Exact ICPN with Level 0 `DISCOVERED` belongs to the Research Registry even when some information fields remain `UNKNOWN / PARTIAL / CONFLICT`; `INFORMATION_COMPLETE` does not change the Catalog Level.

Level 1 requires a concrete source-backed programming route and is the minimum customer-visible IC Selector level. It remains non-programmable and non-Job-selectable. Only `ProgrammingQualification.state == SUPPORTED` derives Level 2 `PROGRAMMABLE` and Job Picker eligibility. Level 3 `PLASMA_VERIFIED` is an additive verified-configuration status. Selector or picker membership never grants Job/Batch execution.

## Examples outside Catalog Level 0 identity

- Does the pinned OpenOCD `lpc2000` ROM IAP algorithm program LPC845 successfully?
- Is the target Part ID present, and does readback verify?
- Can a PPU Site safely supply VDD and program a particular Socket?
- Is the machine configuration `READY` or HIL `PASSED`?

These belong to Level 1 programming relevance, Level 2 Programming Qualification, or Level 3 PLASMA Compatibility—not missing IC Information columns.
