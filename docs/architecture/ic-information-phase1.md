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
4. Phase 1 `IDENTIFIED` grants read-only IC Selector lookup. It does **not** grant `openocd_software_support=SUPPORTED`, Hardware Ready, Job/Batch, Production admission, execution picker eligibility or physical PASS.
5. The distinct owner transition to Phase 2 Programming was approved on 2026-10-15. Phase 1 evidence may be backfilled while reviewing the same official manufacturer documents, but Programming qualification owns the current work. Phase 3 separately validates concrete Site/Adapter/Socket/PPU configurations.

## Catalog surface distinction (owner updated 2026-10-15)

**IC Selector 身分查詢以 `S1 IDENTIFIED` 為資格門檻，非 OpenOCD `SUPPORTED`。**
可查詢／檢視 ≠ Production Admission ≠ 可執行燒錄 ≠ PPU/Socket HIL PASS。
NXP 已驗證之 73 筆新 Phase 1 物料使用獨立的 `visibility=phase1` 身分查詢索引，
未帶參數 API 與 Job/Batch 解析仍只讀 Production Manifest。
`INFORMATION_COMPLETE` 不構成 `IDENTIFIED` 的顯示前提。
其他 Manufacturer 的 Phase 1 索引尚待獨立接入；不得宣稱全面遷移。


There are two different concepts: **IC Information research/detail completeness** versus **default public IC Selector eligibility**. IC information in a research/admin detail view may be incomplete; it does not grant default product Catalog visibility.

Earlier `SUPPORTED-only` public visibility policy was **superseded** by the owner's 2026-10-15 decision: `S1 IDENTIFIED` is searchable, while programming/production execution remains separately gated by Phase 2 and runtime. Issue #849 remains for the wider visibility/deployment migration. Existing UI badges such as "OpenOCD CFG exists" must not be interpreted as software qualification.

## Examples of excluded Phase 1 questions

- Does the pinned OpenOCD `lpc2000` ROM IAP algorithm program LPC845 successfully?
- Is the target Part ID present, and does readback verify?
- Can a PPU Site safely supply VDD and program a particular Socket?
- Is the machine configuration `READY` or HIL `PASSED`?

These are Phase 2 or Phase 3 requirements, not missing IC Information columns.
