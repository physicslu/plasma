# IC Information — Phase 1 evidence and admission contract

Status: **Phase 1 baseline established; Phase 2 owner transition approved 2026-10-15.** Public Catalog/Runtime migration remains separate.

## Right-hand IC details: independent phase ownership

| Section | Phase | Purpose | Is it currently in scope? |
| --- | --- | --- | --- |
| 01 IC Information | Phase 1 | Original manufacturer IC identity / specifications, exact-ICPN evidence, known/unknown per field | BASELINE / BACKFILL ONLY |
| 02 Programming | Phase 2 | Silicon/revision applicability, manufacturer programming specification, OpenOCD target/driver and erase/program/read/verify | YES — CURRENT |
| 03 PLASMA Compatibility | Phase 3 | Versioned PPU/Site/Socket/Adapter + voltage/pin and HIL/physical evidence | NO |

## Phase 1 canonical information fields

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
4. No `openocd_software_support=SUPPORTED`, `Hardware Ready`, public selectable `Catalog`, Job/Batch, Production admission mutation or physical PASS is derived by this phase.
5. The distinct owner transition to Phase 2 Programming was approved on 2026-10-15. Phase 1 evidence may be backfilled while reviewing the same official manufacturer documents, but Programming qualification owns the current work. Phase 3 separately validates concrete Site/Adapter/Socket/PPU configurations.

## Catalog surface distinction

There are two different concepts: **Phase 1 identity visibility** versus **IC Information field completeness**. Under current ADR-0002, an Exact ICPN with Phase 1 `IDENTIFIED` is eligible for IC Selector visibility even when some IC Information fields remain `UNKNOWN / PARTIAL / CONFLICT`.

Phase 2 Programming and Phase 3 PLASMA Compatibility are independent displayed states, not Selector filters. A Phase 1-visible ICPN may therefore show Phase 2 `UNKNOWN` or `UNSUPPORTED` and Phase 3 `NOT_TESTED`. Existing UI badges such as "OpenOCD CFG exists" must not be interpreted as software qualification, and Selector visibility never grants Job/Batch execution.

## Examples of excluded Phase 1 questions

- Does the pinned OpenOCD `lpc2000` ROM IAP algorithm program LPC845 successfully?
- Is the target Part ID present, and does readback verify?
- Can a PPU Site safely supply VDD and program a particular Socket?
- Is the machine configuration `READY` or HIL `PASSED`?

These are Phase 2 or Phase 3 requirements, not missing IC Information columns.
