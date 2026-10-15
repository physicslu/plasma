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

## Implementation Phases — 三階段 IC Detail 與 Exact ICPN 驗收漏斗（修訂草案）

IC Detail 的三個區塊是**不同的證據產品**，同時形成「原廠身分 → 軟體燒錄資格 → 實機相容性」的逐層資格篩選。**P0／P1／P2 僅保留為既有 OpenOCD 研究排序欄位，不得再作為 Phase 完成狀態或階段數量。**

**專案層級狀態（保留原決議）：**Phase 1 原廠資訊基礎架構已建立；Owner 於 2026-10-15 核准啟動 Phase 2 Programming；Phase 3 仍延後。此狀態**不代表**資料庫內每一個 ICPN 都已個別完成 Phase 1 或 Phase 2。

| Phase | UI 區塊 | 個別 Exact ICPN 的進入／完成條件 | 不得推論 |
| --- | --- | --- | --- |
| **Phase 1 — IC Information** | **01 IC Information** | **`IDENTIFIED`**：NXP／ST／Microchip 等原廠的官方料號、物料或 Ordering 表明確確認**完整商用 ICPN**，並能連結其 Base Device／Family 與來源。先收錄身分；Package、Pin Count、Flash、RAM、Working VDD、I/O Supply、Analog Supply、Temperature、Core 等資訊後續補齊。**`INFORMATION_COMPLETE`** 是獨立的欄位品質里程碑，不是 Phase 1 的入門門檻。 | Phase 1 收錄不代表該料號適用某個 CFG，更不代表 OpenOCD 已可燒錄、Catalog 可見或 PPU 實機通過。 |
| **Phase 2 — Programming** | **02 Programming** | **Phase 1 的子集合**：對**精確 ICPN**依原廠 Programming Guide／Reference Manual／Datasheet 及鎖定版本 OpenOCD 驗證 Silicon ID/Revision、Target CFG/Include、Flash Driver、Bank/Geometry/Security 與宣告的 Erase／Program／Read／Verify 操作，完成可追溯的 Programming Profile。只有通過資格審核者為 `openocd_software_support=SUPPORTED`。 | 家族名稱、共用 Core、單獨 CFG 或 Driver 字串，都不足以取得軟體燒錄資格。 |
| **Phase 3 — PLASMA Compatibility** | **03 PLASMA Compatibility** | **Phase 2 的子集合**：至少有一組明確版本化的 **IC／Package＋PPU／Site＋Socket／Adapter**，通過供電、Pin Mapping、SWD／JTAG、保護與實機 HIL。 | 軟體 `SUPPORTED` 不等於 HIL PASS；Catalog 可見或曾做過 HIL，也不能免除當次 Job／Batch 的安全檢查。 |

### 三階段數量契約：統一以 Unique Exact ICPN 計算

在**同一廠商、同一研究庫 Snapshot 與相同 OpenOCD 軟體資格範圍**下：

- **`S1`（Phase 1 Identified）**：已由原廠證實身分、可列入 Phase 1 的完整商用 ICPN 集合。
- **`S1_complete`（Phase 1 Information Complete）**：其中必要 IC Information 欄位均通過證據驗收者；`S1_complete ⊆ S1`，**獨立統計**。
- **`S2`（Phase 2 Supported）**：`S1` 中通過指定 OpenOCD 版本與宣告操作的精確料號軟體資格審核者。
- **`S3`（Phase 3 HIL Passed）**：`S2` 中至少有**一組指定硬體配置**通過實機驗收的精確料號。

**強制不變量：`S3 ⊆ S2 ⊆ S1`，因此 `|S1| ≥ |S2| ≥ |S3|`。** 可以相等；不能把 CFG 數、家族數、Programming Profile 數、Research 候選數、或 HIL 測試次數混入 Exact ICPN 分母。**通過 HIL 的配置組合數另計。**

Phase 2 若不符合、證據不足、在指定 OpenOCD 版本不支援，或日後軟體資格失效，**只是不列入／退出 `S2`，必要時同步退出 `S3`；仍保留在 `S1`**，並記錄不符合原因、Provider 版本及原廠證據。Phase 3 失敗只撤銷該硬體配置的 PASS；同一 ICPN 若無其他通過的配置，才退出 `S3`。唯有**原廠身分本身不成立**，才依獨立 Phase 1 身分修正流程處理。

### Phase 1 — CFG 反向發現入口與原廠權威資料來源

**OpenOCD CFG-first Reverse Discovery 是預設的「研究入口／選料策略」，不是 IC Information 的原廠規格證據。** 任何替代 Provider／版本應依既有政策獨立核准。

1. **由 Config 反推候選 Family／Base Device**：使用指定 OpenOCD 版本／Commit 的 `tcl/target/*.cfg`，遞迴展開 Tcl Include，解析 Target、Flash Bank 與實際 Flash Driver。記錄 Provider、版本、CFG、Driver、來源雜湊，以及映射是否明確／通用／部分成立。單看 CFG 檔名或 Family 前綴不能證明精確 IC 可燒錄。
2. **反查原廠完整料號**：由已辨識家族尋找原廠 Product、Package／Quality、Ordering Table、Datasheet 或官方 Parametric Export。把**該家族中原廠實際列出的各種封裝與商用後綴料號**逐一建檔。**Phase 1 不要求每一個封裝後綴都有獨立 OpenOCD CFG、Driver 或 Silicon ID 證據**；但不能拼湊不存在的料號、把 Product 標題的 Active 當成每個 Material 都 Active，或把只有 Family／DFP Alias 的紀錄冒充完整 ICPN。
3. **`IDENTIFIED` 最低門檻**：`manufacturer`、**完整商用 `icpn`**、由原廠確認的 Base／Family 對應、官方 Source URI、來源證據作用範圍（Material／Ordering 與 Family／Product 必須分清）、觀察時間與身分證據狀態。同一完整商用身分去重；Lifecycle 與材料後綴分開記錄。猜測、模糊命中、衝突或不完整料號保持 `RESEARCH_ONLY`／`IDENTITY_DISPUTED`，**不進 `S1`**。
4. **原始證據封存與 Phase 1 數量分開管理**：能取得時封存原廠 XLSX／PDF／HTML／API 原始 Bytes 與 SHA-256。若無法封存，必須標記 `SOURCE_BYTES_NOT_ARCHIVED`，保留官方 URL、觀察時間、Source Scope，**不可聲稱已保存原廠 Binary SHA 或完整的原始檔位元重播**。但是可由官方**個別物料紀錄直接確認且無歧義**的 ICPN，仍可計為 `IDENTIFIED`；未封存來源須另列缺口。Phase 1 收錄**不自動構成**內部 Production Admission 或公開 Catalog 資格。
5. **欄位持續補強，不阻擋 `IDENTIFIED`**：補齊 `base_device / package / pin_count / flash / ram / working_vdd / io_supply / vdda_or_analog_supply / temperature`，以及適用的 Core／Architecture。保留原始單位、工作模式、文件版次／表格、Exact／Family 適用範圍與 `VERIFIED／PARTIAL／UNKNOWN／CONFLICT`。如原廠明確證明沒有某個獨立電源軌，可使用附證據的 `NOT_APPLICABLE`；不得以 Absolute Maximum Ratings 當 Working VDD，亦不可將 VREF 混為 VDDA。
6. **`INFORMATION_COMPLETE` 門檻**：所有適用的必要欄位均有精確料號或明確涵蓋該料號的 Family 官方證據，結果為 `VERIFIED` 或有來源的 `NOT_APPLICABLE`。必要欄位存在 `UNKNOWN／PARTIAL／CONFLICT` 時不得列為資訊完整，**但不從 `S1` 移除**。來源原檔封存覆蓋率再單獨呈現。
7. **Phase 邊界**：Phase 1 不宣稱 Erase／Program／Verify 可用、不授權 `SUPPORTED`、不建立已驗證 Programming Profile，也不能批次提升 Production／公開 Selector 或實機 HIL。現行內部 Identity Admission 政策維持不變。不從 OpenOCD 開始取得的低成本原廠料號，也仍可保存在 Research；並非禁止保存其他合法來源。

**案例：** 從 `lpc8xx.cfg` 發現家族後，可反查 NXP 官方 LPC811／812／822／824 各自存在的完整商用後綴。每一筆**經原廠個別確認**者即可進入 Phase 1 `IDENTIFIED`；即使某個 Silicon Revision 尚無 `lpc2000.c` 支援證據，也是在 Phase 2 再檢查。**一個 CFG 不等於一個 ICPN，也不代表整個家族已 `SUPPORTED`。**

**Phase 1 驗收輸出：** `S1` Exact ICPN 清單、官方來源與取得時間、Family／Ordering Variant Crosswalk、OpenOCD 研究入口、逐欄位覆蓋率、身分衝突、原始證據封存缺口、可重播的來源檢查，以及獨立的 `S1_complete` 數量。**不得藉此修改 Production／公開 Catalog 或 Phase 2／3 結果。**

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

### Phase 2 — Programming implementation contract（依原廠程式文件做軟體資格篩選）

Phase 2 從 **Phase 1 `IDENTIFIED` 的 Exact ICPN 集合**選取候選，**不使用歷史 P0/P1 數量當作分母**。逐一核對原廠 Programming Guide／Reference Manual／Datasheet 與指定 OpenOCD Provider／版本，確認實際 Silicon ID／Revision、Target/Driver/Flash Bank、ROM IAP 或 Flash Controller、Geometry、Security、Reset/Clock 條件，及宣告的 **Erase／Program／Read／Verify** 操作，建立有版本與適用範圍的可重用 Programming Profile。

- **`SUPPORTED`**：精確 ICPN 的軟體燒錄適用性與宣告操作有足夠、可重播的版本鎖定證據，列入 `S2`；不宣稱 PPU／Socket HIL。
- **`CANDIDATE／UNKNOWN／BLOCKED`**：只有部分 OpenOCD 線索，或必要文件／證據不足、相互衝突；保留在 `S1`，不計 `S2`。
- **`UNSUPPORTED`（限定版本與操作範圍）**：經審核確定該 Provider／版本／操作不適用；保留在 `S1`，不計 `S2`，不可推論全世界任何後端都永遠無法燒錄。
- **退版或資格回歸**：保留原廠料號與歷史證據，撤銷受影響的 `S2` 軟體資格，並重算相關 `S3` 資格。

Phase 2A 可以先建立軟體資格權威，再由 Issue #849 完成公開 Catalog／IC Selector 的 **SUPPORTED-only** 顯示遷移。即使 Phase 1 已收錄、具備某家族 CFG 或已有內部 Production 身分，**也不得在尚未取得 `SUPPORTED` 前自動公開為可燒錄選項**。

### Phase 3 — PLASMA Compatibility handoff（與軟體資格分離的實機相容性）

Phase 3 只把 `S2` 中具有**特定配置實機驗證**的 ICPN 計入 `S3`。驗收證據需鎖定 Device／Package、Socket／Adapter 型號及 Revision、PPU／Site、Pin Mapping、電壓／電流／保護、Debug Interface、PS／PL／OpenOCD 版本及實際 HIL 操作。

`S3` 統計**唯一 Exact ICPN 數**；通過的實體配置或測試次數另外統計。軟體 `SUPPORTED` 而 Socket／PPU `NOT_TESTED` 的 IC，**仍可依既有政策顯示於軟體合格 Catalog**，但不計 `S3`。Job／Batch 對選定 Site 的執行期、安全及供電條件維持 Fail Closed；不得用 Phase 1／2 文件捏造 HIL PASS。

### Visibility and status boundary during phased migration

This ADR's already-accepted final **user-facing default selectable Catalog = exact software `SUPPORTED` only** policy remains unchanged, but it is **not implemented merely by adopting these phases**. Phase 1 IC Information may be examined in internal Research/admin detail views; this does not make incomplete or unqualified ICPNs eligible in the default product selector. The current IC Selector/API visibility migration belongs to Phase 2 (Issue #849) and remains explicitly outstanding. No existing `OpenOCD CFG exists` badge may be interpreted as an affirmative programming-qualification result.

## Phase scope of the existing OpenOCD-first and Core/Driver requirements

OpenOCD-first CFG／Target／Driver 分析是**Phase 1 的預設研究入口**，同時為**Phase 2 的燒錄資格**提供技術證據。Phase 1 的身分權威來源仍是原廠完整商用料號；Phase 2 才判定精確 Silicon／Programming Operation 相容性；Phase 3 才判定指定硬體配置的實機 HIL。P0／P1／P2 僅為舊有內部研究排序，**不得拿來當 `S1／S2／S3` 的 Phase KPI**。

目前整體專案狀態仍為：Phase 1 架構已建立、Phase 2 Programming 已核准執行、Phase 3 延後。專案階段進度**不代表**每顆 Exact ICPN 均已個別通過。舊研究資料、來源 Hash 與未完成的欄位／資格缺口均保留，不得因本次修訂而回溯視為 `IDENTIFIED`、`INFORMATION_COMPLETE` 或 `SUPPORTED`。



## Research prioritization — OpenOCD first (owner-approved)

**PLASMA 的研發資源首先用於目前指定／核准 OpenOCD 版本確實有機會燒錄的 IC。全面保留原廠資料是低成本的 Research Inventory 行為，不代表必須逐顆深入調查。** 此優先級與反向覆蓋流程 **不設 Manufacturer／Brand Allowlist**；適用目前與未來任何可由指定 OpenOCD Provider 取得可信 Flash Programming 來源線索的裝置、Core 及 Debug Transport。ST、NXP、Microchip 僅為既有研究案例，不是適用範圍邊界；執行追蹤見 [Issue #851](https://github.com/physicslu/plasma/issues/851)。

固定優先順序如下：

| Priority | Criteria | Authorized research depth |
|---|---|---|
| **P0 — Programming Path Established (research)** | 指定且鎖定的 OpenOCD Provider 有可解析的 Target CFG／Include Graph、明確 Flash Driver 連結、必要 probe／erase／write／read-or-verify 操作的可信**來源路徑**，及可再驗證的晶片 Part ID 或通用 probe 適用性線索；沒有已知明確反證 | **優先**查證精確商用 ICPN ↔ silicon/revision、Flash geometry／security／operation 與 Phase 2 Profile；**不是**正式 `SUPPORTED`，也不要求先有 HIL |
| **P1 — Programming Path Incomplete** | 指定版本有可追溯的 Target、Driver、晶片或操作線索，但缺少完整路徑、ID、操作適用性或來源證據 | 依固定版本、裝置／家族及明確範圍執行**一次有界查核**；提出升 P0、維持 P1 並 `CLOSED_EVIDENCE_GAP`、或轉 P2 封存的處置及缺口；不得無期限重複搜尋 |
| **P2 — No Established Programming Path / Archive** | 在**明示且固定的檢查範圍**沒有建立可信的 Flash Programming 路徑，**或**依獨立商業需求決策暫緩；不等於全版本永久不支援、非 Active 或 EOL | 保存低成本來源、查核範圍、缺口與暫緩原因；不再一般性逐顆深入研究，直到新的來源版本、原廠證據或核准需求觸發重新開案 |

### Vendor-agnostic OpenOCD Reverse Coverage SOP（研究優先級標準程序）

本節規範 **研究階段的 OpenOCD 能力索引與 P0/P1/P2 優先級**，僅供 Phase 1 CFG-first Reverse Discovery 確定研究入口、以及 Phase 2 重用技術線索。**P0/P1/P2 不是 Phase 1/2/3 的完成狀態；任何符合原廠身分門檻的 Exact ICPN，進入 Phase 1 `S1` 不需要先取得 P0，也不要求每筆料號都有獨立 CFG／Driver。** Phase 2 的 exact-ICPN Software Qualification 和 Phase 3 的 Physical Validation 仍各自獨立。本程序適用所有製造商；起點是 OpenOCD 能力來源，**不是**指定品牌的料號名錄。機器可檢查的政策契約為 [OpenOCD Reverse Research Contract v1](../architecture/openocd-reverse-coverage-research-contract-v1.json)，只鎖定流程和證據欄位，不構成既有資料自動升級的授權。

1. **固定 Provider 與母體邊界：** 使用 `release/openocd.json` 或已核准的 Provider Registry，記錄 Provider、版本、Source Commit、Git Blob、檢查日期、搜尋範圍與明確排除範圍。其他 upstream `master`、Vendor Fork、舊版本各屬獨立 Capability Inventory，不可用未核准版本的結果代替目前版本。明確區分選到的 CFG／Driver 子集合和「所有 OpenOCD 裝置」或「全部原廠 Active 料號」。
2. **先建 Capability Index（由軟體向外查）：** 解析 Target CFG、Tcl Include Graph、Core/Debug Transport、Flash Bank/Driver、Part ID／probe 規則與操作來源（`probe`、必要 `erase`、`write/program`、`read/verify`），保留原始路徑及對應 Git Blob／內容雜湊。主要能力索引鍵為 **`Provider + Version/Commit + Target + Flash Driver + Silicon Identity/Probe Rule`**；Manufacturer、Base Device、Exact ICPN 是後續身分對照，不是底層 Flash 能力主鍵。
3. **反向解析原廠商用料號：** 從來源所指向的 Device/Silicon Family 反查任何製造商的官方 Base Device、**精確可訂購 ICPN**、封裝／物料尾碼、生命週期及原始頁面／文件。分清 `family`、`product`、`material`、`exact ICPN` 證據層級；未確認的訂購碼應保留研究狀態；原廠官方明確確認的 Exact ICPN 依 Phase 1 `IDENTIFIED` 入庫。原始網頁不可取得或未封存 SHA 時，另記錄 `SOURCE_BYTES_NOT_ARCHIVED` 等保管缺口，**不應把來源封存品質與原廠身分是否存在混淆**；不得補造身份或宣稱 Source Replay PASS。
4. **依證據分流：** P0 必須具備版本鎖定的 **Target → Include → Flash Driver → 必要操作來源 → 可信 silicon 適用性** 路徑；通用 Driver probe 可以是待驗證的適用性線索，但單獨的 CFG、Core、SWD/JTAG、Driver symbol 或前綴命中不能構成 P0。P1 保留至少一項真實、可追溯的相關線索，並指出未完成環節。P2 只在本次**受限範圍**未建立可信路徑或有獨立產品排程理由時封存，不做全廠牌或永久不支援結論。優先級與 `UNKNOWN/CANDIDATE/SUPPORTED/UNSUPPORTED` 不是同一種狀態。
5. **P1 僅作一次有界相容性查核：** 定義 `provider/source_commit + device/silicon group + searched CFG/Driver scope` 作為研究工作單位，開始前記錄範圍、接受條件、排除條件與停止條件；結論只能是 `PROPOSE_P0`（提供來源，**待獨立審核**）、`CLOSE_P1_EVIDENCE_GAP`（Priority 仍為 P1，調查狀態 `CLOSED_EVIDENCE_GAP`）、`ARCHIVE_P2`（Priority=P2，附原因）。**P1 調查結案不等於 P1 軟體支援已完成。** 未取得關鍵證據即停止無限期擴查，不以缺證據冒充已證實不可燒錄。
6. **有條件重新開案：** 只因**固定 Provider／Source Commit 有實質變更**、取得新的可驗證原廠／晶片適用性證據，或出現核准的業務需求而重新開啟受影響的 P1/P2，不重跑所有已結案的料號。每次留存前次 Review ID、差異證據與重啟理由；單純要求更多候選數量不構成新證據。
7. **交付與獨立驗收：** 每批輸出可追溯 Source Manifest、Capability Index、Device/Silicon ↔ Manufacturer Base ↔ Exact ICPN Crosswalk、每筆 P0/P1/P2 決策、P1 查核／停止／重啟紀錄及 `source-locked` 差異報告。CI 必須阻擋版本／Git Blob 漂移、假造原始檔雜湊、未經核對的 Exact ICPN、無操作證據升 P0、P1 已結案卻宣稱 `SUPPORTED`、無證據的全製造商覆蓋，以及未授權修改 Production／Selector／Job／HIL。

**必要研究欄位：** `provider`、`provider_version/source_commit`、`target_config`、`include_graph`、`flash_bank_driver`、`operation_source_refs`、`core_model`、`debug_transport`、`silicon_part_id_or_probe_rule`、`manufacturer`（待辨識允許 Unknown）、`manufacturer_source_ref/scope`、`official_base_device`、`exact_orderable_icpn`（未取得不得捏造）、`ordering_identity_state`、`lifecycle_observation`、`evidence_hashes`、`research_priority`、`investigation_state`、`bounded_scope`、`source_checked_at`、`missing_evidence`、`stop_reason`、`reopen_triggers`、`research_owner` 及 `decision_source_ref`。允許部分研究欄位 Unknown，但**絕對不能因預設值自動補成驗證完成**。

**衡量與限制：** 分開統計「每個新 P0 候選研究工時」、「P1 一次有界調查結案率」及「獨立通過 Phase 2 的精確 ICPN `SUPPORTED` 數」。未知全廠商母體不得填入 0%／100%。JTAG、NRND、產品需求及 HIL 與 P0-P1-P2 研究優先級分開紀錄；可影響商業排程，不能倒推成軟體不可用。**本修訂不重分類既有 ST/NXP/Microchip 或其他研究紀錄，不建立任何新的 `SUPPORTED`，不授權 Production、Catalog、Job/Batch 或硬體變更。**

研究順序要**先核對固定 OpenOCD Source/Driver/Target 的可用能力，再將能力對應到 Manufacturer Device Family／Exact ICPN**，而不是先耗費大量時間完整調查所有商用料號後才反向找 OpenOCD 支援。僅用檔名、家族前綴或資料庫 `mapped` 欄位匹配，不得宣稱已達 P0 的正式 `SUPPORTED` 資格。

對既有 **Microchip 24,051 Research 候選 ICPN**，保留全部來源資料即可；目前不再以擴張候選總數或全面補完廠商生命週期為工作目標。**297 個 MCP `NOT_FOUND` 與 68 個 fuzzy-only 查詢**預設留在低優先 backlog，除非先證明其裝置家族屬於 P0/P1。P2 的 Research archival 不等於停產、OpenOCD 永久不支援或已被硬體驗證。

Phase 進度 KPI 以 `|S1|`（原廠已確認完整 ICPN）、`|S1_complete|`（欄位資訊完整）、`|S2|`（OpenOCD software-qualified exact ICPN）、`|S3|`（至少一組 HIL PASS 的 exact ICPN）分別呈現，並檢查 `S3 ⊆ S2 ⊆ S1`。OpenOCD Target/Driver/Profile 數量和 HIL 組態數量另列，不得混入同一分母。工程指標應以「版本鎖定 OpenOCD 可證明的 Device/Driver/Operations → 通過精確 ICPN Software Qualification → Catalog 可見數量」為主要成果指標；24,051 等原始候選數是**獨立的背景庫存指標**，不得納入產品支援率分母或營運承諾。

## Implementation requirements — Core / Transport / Flash-Driver classification (owner-approved)

**MCU Core 是 Research 的搜尋索引與技術分類維度，不是 OpenOCD `SUPPORTED` 的證明或 Catalog 顯示門檻。** 此政策不限定 Manufacturer、Core 架構或 Debug Transport（包含現有及未來可追溯來源的非 ARM Target），並由 [Issue #851](https://github.com/physicslu/plasma/issues/851) 追蹤實作。

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

**後續實作 PR 必須新增的 Phase Funnel 契約測試：**

- 一份 OpenOCD CFG 可反查原廠家族內多個官方完整商用封裝／Ordering Variant；每筆原廠個別證實者可獨立進入 `S1`，不需每筆各有 CFG；**臆造後綴、只有 Product Title 的 Active** 都不得計入。
- 分別報告 `S1`、`S1_complete`、原檔已封存與僅觀察到原廠網頁的比例，以及逐欄位證據狀態；缺失的 VDDA 或原始 Binary 不得假裝 `VERIFIED`。
- Phase 2 證據不足、指定版本不支援時仍保留 `S1`，但排除 `S2` 與 `S3`；不能只因 OpenOCD 不適用就刪除原廠有效料號。
- 三階段均以 **Distinct Exact ICPN** 統計，不得混入 CFG 檔數、Base Device、Family 頁數、Profile 數或 HIL 測試執行次數；每個 Snapshot 驗證 `S3 ⊆ S2 ⊆ S1`。資訊完整數和實體配置組合數獨立報告。
- Phase 3 `HIL PASSED` 必須有指定配置；軟體 `SUPPORTED` 但 Socket 未測的 IC 可以依軟體資格顯示於 Catalog，卻不可列入 `S3`；單一硬體失敗不得直接撤銷 Phase 2。

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
