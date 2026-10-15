# ADR-0002: PLASMA Catalog 以 OpenOCD 軟體燒錄支援為顯示門檻，硬體驗證獨立管理

- **Status:** Accepted (product policy; Phase 1 baseline established; Phase 2 Programming active; public Catalog migration outstanding)
- **Date:** 2026-10-14
- **Scope:** Manufacturer Research / Production Identity Catalog / Product IC Selector / OpenOCD software support / PPU-Site-Socket physical validation
- **Owner decision:** 2026-10-14
- **Tracking:** [Issue #849 — Public Catalog qualification](https://github.com/physicslu/plasma/issues/849), [Issue #851 — OpenOCD-first manufacturer research prioritization](https://github.com/physicslu/plasma/issues/851)
- **Related:** `docs/architecture/icpn-catalog-admission-policy.json`, `data/device-catalog/production/README.md`, `docs/architecture/ic-selector.md`, `docs/architecture/device-support-validation.md`, `docs/architecture/openocd-versioned-provider-registry-v1.md`

## Context

PLASMA 現階段以 **OpenOCD** 為燒錄軟體 Backend。Manufacturer DFP、Product Search 和 OpenOCD target/flash driver 的覆蓋範圍不同。Microchip Research 已保存 24,051 筆不重複、具來源連結的 *候選* ICPN；這不是經獨立核定的 Microchip 全部可訂購 SKU，更不是 PLASMA 已具備燒錄能力的數量。

Socket、Adapter、PPU 與 Site 等實體硬體測試需購置特定封裝的樣品與治具。若把 Socket HIL PASS 當作 Catalog 顯示條件，便會錯誤排除 OpenOCD 已支援、只是尚未備齊實體測試條件的 IC。反過來，若將所有 DFP 或 OpenOCD CFG 文字命中的 IC 直接列為 Supported，也會虛報實際軟體能力。

目前 Production Identity Catalog 的 admission contract 允許 `no_mapping`；IC Selector 也可以呈現已收錄但尚未映射的 exact ICPN。現行產品顯示路徑因此**尚未符合**本 ADR 的「只顯示軟體支援」新規則。不能把決策方向寫成已完成的 runtime 保證。

## Decision

> **PLASMA 面向一般使用者的 Catalog／IC Selector，僅列出有可追溯證據、由指定 OpenOCD 版本支援燒錄操作的精確原廠 ICPN。是否具有 Socket、Adapter、PPU、Site 實機 HIL 證據是獨立狀態，不是 Catalog 顯示資格。**

具體規則：

1. **Manufacturer Research Catalog** 保存原廠發現的候選 ICPN、DFP 裝置名稱、搜尋失敗、生命週期觀測與證據；不受 OpenOCD 支援與否限制，但不得直接進入公開可選擇的 Catalog。
2. **Production Identity Store / Catalog Admission** 管理精確原廠商業 ICPN 與可驗證來源；資料可因歷史／審核用途保留 `no_mapping`，但內部 identity admission 不等於使用者可見、也不等於燒錄能力。
3. **User-facing PLASMA Catalog View**（包括 `GET /api/devices/search` 的預設商品查詢、`catalog_size`、`total_count`、分頁、IC Selector、PMode／EMode picker、分類數量）**僅包含 OpenOCD software-qualified = SUPPORTED 的 exact ICPN**；各入口的數量與集合必須相同。Research-only、unknown、candidate、unsupported、unmapped 不出現在預設產品選料集合。
4. 軟體支援資格要鎖定 **OpenOCD Provider / 版本或 source commit、Target／Device 對應、Flash Driver、必要的 Flash geometry／bank 假設以及 program、必要 erase、read/verify 等實際宣告的 operation 能力**，保留證據與約束。只有 CFG 檔案名稱、家族字首、確定性 `mapped` 路徑或研究候選，**不足以單獨宣告 OpenOCD = SUPPORTED**。不能在無實體的條件下證成必要晶片特性時，維持 Candidate/Unknown。
5. **硬體驗證獨立維度**：分開保存 IC/package、Socket／Adapter 型號與修訂版、PPU/Site 型號、供電與接腳映射、OpenOCD/PLASMA 軟體版本及測試結果。OpenOCD = SUPPORTED 且 Socket = NOT_TESTED 的 exact ICPN **仍應顯示於 Catalog**；UI 必須明示「尚未實機驗證」，不能標成 Hardware Passed。
6. **執行授權仍分離**：Catalog 顯示不代表目前安裝的 PPU Runtime 已安裝相符的 OpenOCD Binary，也不代表 Socket 適配、電壓、安全、Flash 操作限制均滿足。Job/Batch 必須維持既有 runtime/配置/安全條件的 fail-closed 機制。
7. OpenOCD 是**目前產品 Catalog 顯示門檻**，不是永久禁止未來 Vendor Backend / Plasma-native Backend。變更此政策需另行核准並版本化，不能透過暗中放寬篩選達成。

## Implementation Phases — three IC detail sections (owner-directed; source-first funnel)

The three IC Detail panels are **three distinct, independently auditable evidence products**. Their scope is also a progressive **exact-ICPN qualification funnel**, not P0/P1/P2 research-priority labels. The legacy P0/P1/P2 fields are retained as historical research prioritization metadata, **not a Phase completion state or phase-count denominator**.

**Project delivery history:** Phase 1 manufacturer-information baseline established; owner authorized Phase 2 Programming on 2026-10-15; Phase 3 remains deferred. This does **not** mean every researched exact ICPN has individually passed Phase 1 or that Phase 2 has certified it.

| Phase | IC Detail panel | Inclusion/acceptance for a single exact commercial ICPN | Independent non-claim |
| --- | --- | --- | --- |
| **Phase 1 — IC Information** | **01 IC Information** | **`IDENTIFIED`**: a genuine, complete commercial manufacturer ICPN is individually evidenced by an official manufacturer part/material/ordering source, with family/base-device link and provenance. Register the identity first; continue filling package, pins, Flash, RAM, working VDD, I/O supply, analog supply, temperature and Core evidence. **`INFORMATION_COMPLETE`** is an additional, separately measured field-quality milestone, not the entrance requirement. | Being in Phase 1 does **not** prove applicability to the discovered OpenOCD CFG, programming support, public Catalog visibility or a physical PPU. |
| **Phase 2 — Programming** | **02 Programming** | Subset of Phase 1 whose **exact ICPN** has version-pinned OpenOCD software qualification: applicable silicon identification/revisions, Target Config/include graph, Flash Driver, geometry/banks/security, and declared erase/program/read/verify behavior justified against the manufacturer Programming Guide/Reference Manual/Datasheet; store a scoped, reusable Programming Profile. Only independently qualified devices receive `openocd_software_support=SUPPORTED`. | A family CFG, Core, Flash Driver name, Phase 1 evidence or installed-runtime assumption alone never qualifies software support. |
| **Phase 3 — PLASMA Compatibility** | **03 PLASMA Compatibility** | Subset of Phase 2 with **at least one explicitly identified PPU/Site/Socket/Adapter/target-package configuration** passing applicable power, pin-map, SWD/JTAG, safety and real-hardware HIL evidence; preserve hardware/software revision identifiers. | Phase 2 SUPPORTED does not imply HIL PASS, and neither Catalog visibility nor a past HIL PASS waives selected-site Job/Batch execution safety checks. |

### Phase count contract — use exact ICPNs, not CFG files or test runs

For a **fixed manufacturer, inventory snapshot and approved OpenOCD software-qualification scope**, define the sets of **unique exact commercial ICPNs**:

- `S1`: official-manufacturer identity `IDENTIFIED` in Phase 1.
- `S1_complete`: Phase 1 identities whose required information fields independently meet the information-completeness contract. `S1_complete ⊆ S1`; this number must be **reported separately**.
- `S2`: Phase 1 identities that have passed scoped **Phase 2 OpenOCD software qualification** (`SUPPORTED`).
- `S3`: Phase 2 identities with at least one **Phase 3 physical HIL PASS** tied to a specific, immutable hardware/site/socket configuration.

**Mandatory invariant:** `S3 ⊆ S2 ⊆ S1`, therefore `|S1| ≥ |S2| ≥ |S3|`. Equality is permitted; mixing a family/Target/Driver count, raw Research candidate count or *number of HIL configurations* with exact ICPN counts is prohibited. Report the configuration-level HIL count as a **separate metric**.

Phase 2 **failure, unsupported-in-pinned-version, insufficient evidence or later regression removes/withholds the exact ICPN from `S2`** and consequently `S3`, **not** from `S1`. It must remain discoverable in internal Phase 1 Research with the reason and source/version retained. Phase 3 HIL failure removes/withholds **that configuration** and adjusts `S3` only when no qualifying configuration remains; it does not invalidate genuine IC identity or automatically revoke Phase 2 software evidence. A withdrawn/invalid manufacturer ICPN identity is handled by a **separate Phase 1 identity correction**, not by a Phase 2 rejection.

### Phase 1 — discovery entrypoint vs authoritative IC Information

**OpenOCD CFG-first Reverse Discovery is the default *research discovery and work-selection entrypoint*, not an official manufacturer IC Information source.** A vendor-supported alternative provider/version requires separate approval under the existing provider policy.

1. **Discover candidate base devices/families** from the version-/commit-pinned OpenOCD `tcl/target/*.cfg` tree, recursively resolved Tcl includes, instantiated Target/Flash-bank configuration and actual Flash Driver source. Retain provider, commit, CFG and relevant Driver hash, and whether the route is concrete, generic, partial or missing. A CFG filename or a family substring **never alone demonstrates per-ICPN programming support**.
2. **Reverse-map to the original manufacturer** using official Product/Package & Quality pages, original Parametric/Ordering tables, device datasheets or equivalent authoritative, scoped exports. Enumerate the **real, observed exact commercial ICPNs** across that manufacturer-confirmed family, including package/ordering variants. **Do not require an independent CFG file, Flash Driver match or verified silicon ID for every variant to enter `S1`.** Conversely, never synthesize order codes from prefixes, infer a material's Active state from a product header, or equate a family heading/DFP alias with an exact ICPN.
3. **Phase 1 entry (`IDENTIFIED`)** requires at least: `manufacturer`, complete exact commercial `icpn`, manufacturer-verified base/family relationship, official source URI and source scope (material/order code vs family/product), acquisition/observation time, and explicit identity-evidence status. Dedupe on complete manufacturer commercial identity; preserve lifecycle and material variants separately. An incomplete, inferred, contradictory or fuzzy match remains `RESEARCH_ONLY` / `IDENTITY_DISPUTED`, **outside `S1`** until resolved.
4. **Source custody is a separate evidence-quality metric.** Archive original official XLSX/PDF/HTML/API bytes with SHA-256 when obtainable. If access/retention prevents archival, retain the official URL, dated observation, scope and **`SOURCE_BYTES_NOT_ARCHIVED`** caveat; do not fabricate a manufacturer-binary hash or label this source independently byte-replay `VERIFIED`. Such a directly observed **unambiguous official exact material identity** can still be `IDENTIFIED` and counted in `S1`; count and report the custody gap separately. Internal Production identity admission and public Catalog publication remain **independent, stricter decisions**.
5. **Enrich fields continuously**, not as a reason to delay `IDENTIFIED`: `base_device`, `package`, `pin_count`, `flash`, `ram`, `working_vdd`, `io_supply`, `vdda/analog_supply`, `temperature`, optional `core_architecture/core_model`. Keep exact units, operating modes, official document/revision/table, and source applicability. Per-field evidence is `VERIFIED / PARTIAL / UNKNOWN / CONFLICT`; a rail demonstrably absent on a device may be `NOT_APPLICABLE` **only with explicit source evidence**. Do not substitute Absolute Maximum Ratings for working VDD or confuse VREF with VDDA.
6. **`INFORMATION_COMPLETE` gate:** all applicable mandatory Phase 1 fields must have sourced exact-part (or explicitly applicable family-wide) `VERIFIED` evidence, or properly sourced `NOT_APPLICABLE`. Any required `UNKNOWN`, `PARTIAL` or `CONFLICT` prevents information-complete status **without deleting the ICPN from `S1`**. Report per-field coverage and immutable-source custody separately.
7. **Phase boundary:** no Phase 1 software `SUPPORTED`, Programming Profile qualification, erase/program/verify claims, Production/Public Selector mass admission, or physical HIL promotion. Current internal Production identity admission policy is preserved. Non-OpenOCD-started low-cost official manufacturer identities may still be retained in **Research**; this discovery priority is not a prohibition against legitimate source capture.

**Example:** A pinned `lpc8xx.cfg` family lead may generate manufacturer-source crosswalk work for official LPC811/812/822/824 **commercial ordering variants**. All **individually manufacturer-confirmed** variants can enter Phase 1 `IDENTIFIED` even if `lpc2000.c` does not recognize a particular silicon/revision. That exact route is evaluated only at Phase 2. One CFG does not equal one ICPN and does not make an entire family software `SUPPORTED`.

**Phase 1 deliverables / acceptance:** an auditable `S1` exact-ICPN inventory, official source and acquisition metadata, family/variant crosswalk and discovery route, per-field evidence/coverage ledger, identity disputes, custody gaps, reproducible source locks where available, tests and a clearly separated `S1_complete` count. No automatic change to Production admission or default software-qualified Catalog visibility.

### Phase 1 — official manufacturer bulk information acquisition (Microchip initial implementation)

**Decision / implementation method:** Use the manufacturer's **Parametric Search chart export → official MCP exact-ordering crosswalk → targeted datasheet evidence** as the default Microchip Phase 1 acquisition pipeline. This is an **approved workflow contract**, not a statement that a chart exporter, unattended scraper, or all-Microchip complete ingestion already exists. Other manufacturers may use equivalent official, source-bound bulk exports under the same field-level contract.

| Evidence layer | Acquisition and role | Evidence limitation |
| --- | --- | --- |
| **A. Parametric Search / XLSX (bulk)** | Navigate the official Microchip product category/MCU subcategory chart; use **Download Chart → All Data** to export the chart's products **and columns** as XLSX; retain the original file and chart URL/category. Manufacturer guide: [DS00004852A](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/MarketCommunication/Promotions/Parametric-Search-User-Guide-00004852.pdf), “Download Chart Button”; [current online guide](https://www.microchip.com/en-us/products/selection-tools/parametric-search-landing-page/user-guide). | **All Data is chart-scoped**, not all Microchip exact commercial ordering codes or all lifecycle states. A chart row can represent a base device rather than an orderable SKU; available columns vary by chart. A successful file export is a source capture, not automatic per-ICPN verification. |
| **B. Microchip official MCP (exact-ordering evidence)** | Query the [official Microchip MCP product server](https://www.microchip.com/en-us/resources/model-context-protocol-server) via documented Streamable HTTP endpoint `https://api.microchip.com/mcp/resources`, using bounded `search_products` queries and checked pagination; archive original requests/responses. Extract exact `partNumber`, source-provided `basePartNumber`, package/lead count and other actually returned fields. | Search is **not a proven complete enumeration API**. Related/fuzzy hits, vendor base aliases, missing/ambiguous results, or `NOT_FOUND` do not establish full SKU coverage, EOL, or silicon compatibility; fields absent from a response remain unknown. |
| **C. Manufacturer datasheet / ordering table (targeted gaps)** | For absent or conflicting fields, obtain the official versioned family/device document and bind **revision + exact ordering table / electrical table + page or section + applicability** to each finding. In particular distinguish working VDD, `VDDIO`, `VDDA`/`VDDANA` and internal rails such as `VDDCORE`. | Family electrical specs require exact-variant applicability checks; a family table alone stays `PARTIAL`. Only a source explicitly applying a field to an exact ICPN can justify `VERIFIED` for that field. Do not retrieve Programming Guide/Flash-controller semantics in Phase 1. |

**Execution sequence (source-first, repeatable, fail closed):**

1. **Select bounded cohort and chart:** prioritize the previously identified P0/P1 research families for **IC Information only**, starting from the two existing ATSAMD21G18A pilot order codes. Record manufacturer, chart URL/ID, category/subcategory, selection/view settings, export scope, acquisition time and any manufacturer-published source revision/date **separately**. A manual XLSX export is acceptable as an initial capture; no undocumented export API or bypass of HTTP 403 is assumed or authorized.
2. **Archive original bytes before parsing:** store the unmodified XLSX/PDF/MCP response bytes and SHA-256 (and capture manifest containing URL, timestamp, media type, file size, chart/document identifier, acquisition outcome and licensing/access limitations). Verify hashes in an independent offline replay. Temporary CI artifacts with expiration are **not** permanent source archives; unavailable sources record explicit blockers rather than invented hashes.
3. **Normalize chart fields without fabricating evidence:** preserve the exact raw column name, raw value, original units, chart scope and provenance per field. Map only observed data into `manufacturer/icpn/base_device/package/pin_count/flash/ram/vdd/io_supply/vdda/temperature` and optional `core_architecture/core_model`; keep unmatched columns and nulls. Never silently coerce `UNKNOWN` to 0, treat KB as KiB, or apply a base-device number to every commercial suffix.
4. **Crosswalk commercial ICPNs:** use separately archived, bounded MCP query/pagination results and official exact ordering-code tables to build **`exact ICPN ↔ manufacturer-reported base device ↔ chart family row`** links. Deduplicate on complete original commercial order code; quarantine fuzzy matches and conflicting identities. Only exact-source rows may substantiate exact package, pin and temperature fields. A chart-only family value may be useful `PARTIAL` evidence but cannot be auto-upgraded to exact `VERIFIED`.
5. **Resolve missing supply fields selectively:** inspect the official datasheet's *power-supply and operating conditions* material only when the chart/MCP omits or contradicts a Phase 1 information field. Retain distinct rail names, mode/temperature/voltage conditions and any restrictions on multiple supplies; leave unjustified `io_supply` or `vdda` as `UNKNOWN` or `PARTIAL`, not copies of `vdd`.
6. **Reconcile independently:** attach a source locator, original record/cell or document table, version and original-byte reference to **each** field. Track `VERIFIED / PARTIAL / UNKNOWN / CONFLICT` separately; preserve conflicting observations without winner-by-precedence. No automatic Research→internal `ADMITTED`, Production, software `SUPPORTED`, public selector or physical readiness promotion.
7. **Emit auditable Phase 1 deliverables:** create source manifest/immutable raw-source references, a normalized exact-ICPN research ledger, exact-vs-family evidence crosswalk, per-field coverage and conflict report, and deterministic offline replay/negative tests. Report denominators **per chart/category, observed base devices, observed exact ordering codes, independently admitted identities**, and missing/unresolved rows separately; never interpret a chart or MCP search count as Microchip-wide SKU coverage.

**Acceptance / stop gates:** Test an original-byte replay; reject SHA/version mismatch, duplicate/ambiguous exact order codes, family→exact `VERIFIED` promotion, missing units/source locator, false completeness claims and any Production/Phase 2/3 write. If chart export, MCP capture or datasheet access fails, preserve `SOURCE_NOT_AVAILABLE`/coverage gaps and stop that lane or retry only by a permitted official mechanism. Completion is a **reviewable Phase 1 information cohort with quantified coverage**, not a programming qualification; subsequent cohorts and any identity admission remain separately reviewed. The existing Microchip Research inventory (24,051 source-linked candidates) is **not** automatically bulk-enriched or admitted by this decision.

### Phase 2 — Programming implementation contract (active; filtered software qualification)

Phase 2 consumes the **Phase 1 `IDENTIFIED` exact ICPN set**, not the historical P0/P1 count. Verify manufacturer Programming Guide, Reference Manual and applicable Datasheet against the **PLASMA-pinned OpenOCD Provider and source/runtime version**, actual silicon ID/revision, Target/Flash-bank applicability, ROM IAP or controller, geometry/banks/security, reset/clock dependencies, and declared **erase/program/read/verify** operations. Build version-scoped reusable Programming Profiles and reviewed exact-ICPN applicability records.

- **`SUPPORTED`:** sufficient independent, exact-ICPN-scoped version-locked software evidence for the specifically claimed operations; add to `S2`. It does **not** assert physical PPU or Socket HIL.
- **`CANDIDATE` / `UNKNOWN` / `BLOCKED`:** credible partial source leads or unavailable/conflicting essential evidence; remain in `S1` but do not enter `S2`.
- **`UNSUPPORTED` (version/scope-specific):** an independently reviewed negative support outcome for the pinned Provider/version/operations; remain in `S1`, out of `S2`. Do not interpret it as globally or permanently unsupported by every backend.
- **Software regressions:** revoke the affected `S2` software qualification after evidence review and recompute downstream `S3` ICPN eligibility; keep historical identities, sources, and negative findings.

Phase 2A may establish qualification authority before the support-only public Catalog migration under Issue #849. **Only `S2` should be visible by default once that migration is implemented**; Source CFG, historical internal Production identity admission or `S1` membership alone do not authorize it.

### Phase 3 — PLASMA Compatibility handoff (deferred; configuration-bound HIL)

Phase 3 may only count an `S2` exact ICPN after qualified **physical configuration-specific** evidence (device/package + Socket/Adapter model/revision + PPU/Site + pin mapping + voltage/current/protection + interface + firmware/PL/OpenOCD versions and actual HIL operations). Preserve full configuration identity and test result; `S3` counts **unique qualifying ICPNs**, and physical test configurations are separately counted.

Software `SUPPORTED` with Socket/PPU `NOT_TESTED` remains eligible for the **software-qualified Catalog**; it is not counted in `S3`. Job/Batch retains independent selected-site runtime/electrical/safety checks and fails closed. No Phase 1 or 2 artifact can synthesize a HIL PASS.

### Visibility and status boundary during phased migration

This ADR's already-accepted final **user-facing default selectable Catalog = exact software `SUPPORTED` only** policy remains unchanged, but it is **not implemented merely by adopting these phases**. Phase 1 IC Information may be examined in internal Research/admin detail views; this does not make incomplete or unqualified ICPNs eligible in the default product selector. The current IC Selector/API visibility migration belongs to Phase 2 (Issue #849) and remains explicitly outstanding. No existing `OpenOCD CFG exists` badge may be interpreted as an affirmative programming-qualification result.

## Phase scope of the existing OpenOCD-first and Core/Driver requirements

OpenOCD-first CFG/Target/Driver analysis provides the **default Phase 1 research discovery route** and supplies technical evidence for **Phase 2**. Original manufacturer **exact orderable identity** remains the Phase 1 source of truth; programming operation evidence and exact silicon applicability are Phase 2 gates, and configuration-specific physical HIL is Phase 3. The historical P0/P1/P2 OpenOCD-first classification is **internal research priority only** and SHALL NOT be used as `S1`/`S2`/`S3` progress.

The global project baseline remains: Phase 1 framework established, Phase 2 Programming work authorized, Phase 3 deferred. These project statuses are not automatically per-ICPN passes. All preexisting original-source locks and unfinished exact/field qualification gaps remain intact; this policy does not retroactively mark them complete.

## Research prioritization — OpenOCD first (owner-approved)

**PLASMA 的研發資源首先用於目前指定／核准 OpenOCD 版本確實有機會燒錄的 IC。全面保留原廠資料是低成本的 Research Inventory 行為，不代表必須逐顆深入調查。** 這是整個 ST、NXP、Microchip 等廠商通用的持續作業原則，執行追蹤見 [Issue #851](https://github.com/physicslu/plasma/issues/851)。

固定優先順序如下：

| Priority | Criteria | Authorized research depth |
|---|---|---|
| **P0 — OpenOCD software-backed** | 指定版本 OpenOCD 的 Target + Flash Driver + 必要程式操作具版本鎖定來源證據，且具體 IC/variant 適用性可進一步驗證 | **優先**審核精確商業 ICPN、Flash geometry/operations、必要電氣條件、可重用 Profile、相關軟體測試；達到本 ADR 獨立的 software qualification 才准公開 Catalog |
| **P1 — Bounded OpenOCD candidate** | OpenOCD 有可信的 Target/Driver 家族線索，但精確 IC 或 operation applicability 尚不完整 | **一次有界、明確範圍**的 Source/Driver/IC 相容性查核；證據不足便保留 Candidate/Unknown 並停止延伸，不自動變更支援宣告 |
| **P2 — Archive only** | 無可信的指定 OpenOCD Flash programming 支援路徑，或不屬目前產品需要 | **只保存低成本來源資料**（名稱、來源、識別證據、既有原廠觀測與取得時間／雜湊）。停止一般性逐顆 datasheet 深究、訂購碼／EOL 全面追查、封裝／Socket／Programming Profile 建置；除非 OpenOCD 能力改變、客戶有需求或 Owner 明確要求 |

研究順序要**先核對固定 OpenOCD Source/Driver/Target 的可用能力，再將能力對應到 Manufacturer Device Family／Exact ICPN**，而不是先耗費大量時間完整調查所有商用料號後才反向找 OpenOCD 支援。僅用檔名、家族前綴或資料庫 `mapped` 欄位匹配，不得宣稱已達 P0 的正式 `SUPPORTED` 資格。

對既有 **Microchip 24,051 Research 候選 ICPN**，保留全部來源資料即可；目前不再以擴張候選總數或全面補完廠商生命週期為工作目標。**297 個 MCP `NOT_FOUND` 與 68 個 fuzzy-only 查詢**預設留在低優先 backlog，除非先證明其裝置家族屬於 P0/P1。P2 的 Research archival 不等於停產、OpenOCD 永久不支援或已被硬體驗證。

Phase 進度 KPI 以 `|S1|`（原廠已確認完整 ICPN）、`|S1_complete|`（欄位資訊完整）、`|S2|`（OpenOCD software-qualified exact ICPN）、`|S3|`（至少一組 HIL PASS 的 exact ICPN）分別呈現，並檢查 `S3 ⊆ S2 ⊆ S1`。OpenOCD Target/Driver/Profile 數量和 HIL 組態數量另列，不得混入同一分母。工程指標應以「版本鎖定 OpenOCD 可證明的 Device/Driver/Operations → 通過精確 ICPN Software Qualification → Catalog 可見數量」為主要成果指標；24,051 等原始候選數是**獨立的背景庫存指標**，不得納入產品支援率分母或營運承諾。

## Implementation requirements — Core / Transport / Flash-Driver classification (owner-approved)

**MCU Core 是 Research 的搜尋索引與技術分類維度，不是 OpenOCD `SUPPORTED` 的證明或 Catalog 顯示門檻。** 此政策適用 Microchip、ST、NXP 及後續所有 MCU 廠商，並由 [Issue #851](https://github.com/physicslu/plasma/issues/851) 追蹤實作。

### 1. Core-first Research Classification

研究記錄須分開管理下列資訊，禁止以單一 `architecture` 或 `supported` 布林值取代：

| Dimension | Minimum representation | Authority |
|---|---|---|
| `core_architecture` / `core_model` | ARM Cortex-M0/M0+/M3/M4/M7、ARM7、MIPS、AVR 等；不確定時為 `UNKNOWN`；多核心允許明確的多值組合 | 原廠裝置文件／受審核的 Device Pack 及 OpenOCD Target 核心模型；兩者衝突時隔離 |
| `debug_transport` | 依具體裝置和 OpenOCD Target 可用的 SWD、JTAG、其他，允許多值／`UNKNOWN` | 指定 OpenOCD 版本 Target Config 與原廠 Debug 規格，不能僅從 Core 推論 |
| `openocd_provider` / `source_commit` | 指定 OpenOCD Provider 與完整來源版本、若有則安裝 Runtime identity | `release/openocd.json` 或另行核准且來源鎖定的 Provider registry |
| `target_config` / `flash_driver` | 實際解析出的 Target Config、Flash Bank／Driver、相關 Source/Blob hash | 與 Provider 相同版本的實際 Tcl include graph、Flash driver source |
| `flash_operations` | 有範圍限制的 `probe`、`erase`、`program/write`、`read/verify` 能力及限制 | 指定 Driver 實作與目標裝置適用性證據 |
| `exact_icpn_applicability` | 商業訂購 ICPN → underlying silicon/device/revision → target/driver/profile 的可稽核對照 | 原廠商用料號身分與裝置差異證據；不得只憑家族前綴或相同 Core 推廣 |
| `physical_validation` | Socket、Adapter、Site／PPU 個別的 `NOT_TESTED`／`READY`／`PASSED`／`FAILED` 與配置版本 | 獨立 HIL 證據，非 Catalog 軟體顯示門檻 |

必須保留 **Core → Debug Transport → OpenOCD Target → Flash Driver → Exact ICPN** 的關係及來源指標。此關係是**調查與資格審核流程**，不是單向蘊含的支援證明：同為 Cortex-M4、同走 SWD，仍可能使用完全不同的 Flash Controller／Memory Geometry／Security/Reset 程序。

### 2. Driver-first Software Qualification

- 先從 PLASMA **指定版本**的 OpenOCD source/CFG/Driver 建立能力清單，再對應 Manufacturer Core/Device Group 和精確 ICPN；不得把較新 `master` 或 vendor fork 的研究結果直接當成目前 `release/openocd.json` 的可用能力。
- `Target CFG exists`、`Core recognized`、`SWD/JTAG reachable`、`Flash Bank declared` 分別只是不同深度的**研究證據**；其中任一項單獨成立，都不等於已通過 Flash erase/program/verify 軟體支援資格。
- 對符合 P0 Source-backed 的族群，須個別確認 Flash driver 操作、晶片識別／revision、bank/base/geometry、所需 transport、目標限制以及精確料號映射；若任一關鍵證據不足，維持 `CANDIDATE`／`UNKNOWN`，不宣稱 `SUPPORTED`。
- JTAG 不限 ARM；Microchip PIC32MX/MIPS 與部分 AVR JTAG 是非 ARM 路線的優先檢查範例。SWD 對 Cortex-M 特別常見，但不得假設所有 ARM MCU 都可由 PLASMA 所選 OpenOCD Flash Driver 燒錄。
- P0/P1/P2 是**研究資源優先級**；`UNKNOWN/CANDIDATE/SUPPORTED/UNSUPPORTED` 是**軟體支援資格狀態**。兩種 enum 不可混用。P0 也**不自動等於** `SUPPORTED`。

### 3. Core-aware Coverage Metrics

報表最少以 `manufacturer × core_architecture/core_model × debug_transport × provider_version × flash_driver` 分組，並**明確分開不同母體與顆粒度**：

1. 原廠 Research 候選身分數（DFP 名稱或精確 ICPN 需分開；未完成商業身分校驗者不可混入精確 ICPN 總數）。
2. OpenOCD Target／Driver source-backed **Device/Profile** 數量（不是精確 ICPN 數）。
3. 已完成 OpenOCD 軟體 `SUPPORTED` 的 **精確 ICPN** 數量與預設 PLASMA Catalog 可見數。
4. 已完成特定 Socket／PPU／Site Configuration HIL 的數量（不是軟體支援 ICPN 數）。
5. `CANDIDATE`、`UNKNOWN`、`UNSUPPORTED`、P2 Archive-only 分別統計，不能以 0 代替未知。

若要驗證「OpenOCD 支援的 IC 以 ARM 為多數」，必須先固定 **Provider／版本、Microchip 或跨廠範圍、統計單位（Target、Device/Profile、精確 ICPN）和母體**，再計算各 Core 比例；不允許以 Target Config 檔案數、Research 24,051 候選數或對 Cortex-M 生態的直覺直接宣稱多數。未知／未分類的比例必須揭露。

**Migration boundary:** 此節為已批准的架構實作要求，**不是目前 Catalog API、IC Support Schema 或 Microchip ICPN 資格審核已完成的聲明**。不得藉此更新 Production ICPN 或變更 Job/Batch 安全驗證；實作仍需單獨 PR／CI／Owner Merge Gate。

## Status dimensions

建議的邏輯維度如下（**為政策模型，並非宣稱現行 API 已有同名欄位**）：

| Software state | Qualification | Default product Catalog |
|---|---|---|
| `UNKNOWN` | 尚無足夠證據 | 不顯示 |
| `CANDIDATE` | 部分 OpenOCD Target/Driver 線索，尚未達可證明燒錄條件 | 不顯示 |
| `SUPPORTED` | 版本鎖定、IC 對應、Flash 操作範圍及來源證據達成軟體支援審查 | **顯示** |
| `UNSUPPORTED` | 已審查所指定版本不支援 | 不顯示 |

硬體可以另行記錄 `NOT_TESTED`、`READY`、`PASSED`、`FAILED`，但實際上 **Socket / Adapter / PPU / Site 應是不同的、有版本與 Configuration identity 的證據**，不應用單一扁平狀態掩蓋設備和治具差異。

範例：`openocd_software_support=SUPPORTED` 且 `socket_validation=NOT_TESTED`，IC 可以被搜尋與選取；是否能對某座 Site 執行燒錄，由執行階段另行判定，不應自動允許寫入。

## Migration gap and ownership

- **Accepted now:** 產品政策與證據界線。
- **Not yet implemented:** 新版 public visibility gate、可執行的 OpenOCD software qualification schema、統一 API／UI 集合、遷移後的實際支援數量。
- 現行 `docs/architecture/icpn-catalog-admission-policy.json` 的 `requires_deterministic_backend_route_or_explicit_mapping_state`，是內部 **identity admission** 契約，**不得被誤讀為 Public Catalog 可見規則**。
- 現行 `backend.mapping_status=mapped` 主要表示確定性路由，尚不能概括為已做所有 software qualification；`no_mapping` 更不能當 Supported。Research `backend_candidate` 不可轉為可執行路由。
- 保留既有 Production exact ICPN 資料與研究證據，不透過本 ADR 刪除或大規模匯入 Production rows。
- 後續實作由 [Issue #849](https://github.com/physicslu/plasma/issues/849) 追蹤，須分開審查 source/version qualification、Product API／UI 及 execution gate regression。ST、NXP、Microchip 使用**同一套政策**；不得對不同廠商放寬。

## Validation / acceptance

**Additional Phase-funnel contract tests required for subsequent implementation PRs:**

- Source-first example: one pinned OpenOCD CFG may discover a manufacturer family with several official exact commercial package/ordering variants; each manufacturer-attested code is individually eligible for `S1`, with no per-variant CFG prerequisite. An invented suffix or product-heading-only lifecycle must **not** be counted.
- Separately report `S1` identities, `S1_complete` information-complete identities, archived-vs-observed-only original bytes and per-field evidence; missing VDDA or source archive is not silently `VERIFIED`.
- Phase 2 insufficient evidence or unsupported-in-this-version keeps the exact identity in `S1` but excludes it from `S2` (and `S3`). A device is not removed from manufacturer research solely because OpenOCD programming is unqualified.
- Count **distinct exact ICPNs** at each Phase, not CFG files, Base Devices, vendor family pages, Programming Profiles or HIL configuration runs. Independently assert `S3 ⊆ S2 ⊆ S1` on every snapshot. Keep `S1_complete` and physical configuration count as separate metrics.
- Phase 3 `HIL PASSED` is configuration-specific; a software-qualified, socket-untested ICPN remains eligible for software Catalog but not `S3`; a failed configuration does not automatically revoke software qualification.

1. 使用完整 Production manifest 的實際 loaded rows，分別報告 **內部 admitted ICPNs** 與 **軟體已確認 SUPPORTED 的可見 ICPNs**，不手填或繼承歷史 coverage 數。
2. 測試 exact ICPN 有原廠證據但 `no_mapping`、僅 family-matched CFG、只有 candidate source、缺乏可用 Flash driver/operation 證據的資料，皆不出現在預設產品搜尋、picker 和計數。
3. 測試 OpenOCD 已 SUPPORTED，但 Socket／PPU 未測試的 ICPN **仍顯示**，同時標記 Physical Validation 尚未通過。
4. API、UI、分頁、結果總數、Vendor／Family counts 使用同一個軟體支援決策集合；避免 counts 包含隱藏資料。
5. 保持 Job／Batch 的 runtime executable、選定 Site、電氣限制、配置安全與硬體審核獨立 fail-closed；嚴禁由 Catalog presence 推導可執行。
6. Research-only Microchip 24,051 候選與原廠資料庫不受顯示規則刪除或修改。
7. Core／Transport／Target／Flash Driver／Exact ICPN 每一層具可審核來源與版本，且測試同 Core 但不同 Flash Driver 不得被誤判可互換；多核心或未知 Core 不可被強制歸類為 ARM。
8. 測試 Cortex-M/SWD/CFG-only 仍為 `CANDIDATE` 或 `UNKNOWN`，以及 MIPS/PIC32MX 或 AVR/JTAG 等**非 ARM**來源線索可進行同等審核；P0 Source-backed 不得自動晉升 `SUPPORTED`。
9. Core 統計顯式標明 OpenOCD 版本與 Target／Device/Profile／精確 ICPN 各自分母，並分別報告 P0/P1/P2 與軟體資格狀態；不得以 24,051 研究候選作為已支援分母，也不得未經統計就宣稱 ARM 占多數。

## Alternatives considered

- **只要原廠候選料號就全部公開**：拒絕；對目前 OpenOCD-only 產品會誤導使用者。
- **只公開 Socket/實機 HIL PASS**：拒絕；把硬體可取得性誤當作 OpenOCD 軟體支援邊界。
- **只要有 OpenOCD CFG 或 mapped 欄位就公開**：拒絕；Target CFG/路由未必代表版本適用且具備可用 Flash 燒錄能力。
- **Research 全部保留，公開只顯示軟體已驗證支援**：**採用**；保留市場發現能力且降低產品支援誤報。

## Decision summary

```text
All manufacturer discovery/evidence → Research (retained)
       ↓ authoritative exact ICPN identity
Production internal identity admission (may include unmapped)
       ↓ pinned OpenOCD software programming qualification
User-facing PLASMA Catalog (SUPPORTED only)
       ├── Socket / Adapter / PPU / Site physical validation (independent)
       └── selected-site runtime and safety execution gate (fail closed)
```
