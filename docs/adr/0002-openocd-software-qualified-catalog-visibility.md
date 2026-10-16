# ADR-0002: PLASMA IC Discovery、Phase 狀態與 Catalog 可見性統一政策

- **Status:** Accepted (cross-vendor Phase 1/2/3 policy; Phase 1 identity visibility approved; Phase 2 Programming active)
- **Date:** 2026-10-14
- **Scope:** Manufacturer Research / Production Identity Catalog / Product IC Selector / OpenOCD software support / PPU-Site-Socket physical validation
- **Owner decision:** 2026-10-14
- **Tracking:** [Issue #849 — Public Catalog qualification](https://github.com/physicslu/plasma/issues/849), [Issue #851 — OpenOCD-first manufacturer research prioritization](https://github.com/physicslu/plasma/issues/851)
- **Related:** `docs/architecture/icpn-catalog-admission-policy.json`, `data/device-catalog/production/README.md`, `docs/architecture/ic-selector.md`, `docs/architecture/device-support-validation.md`, `docs/architecture/openocd-versioned-provider-registry-v1.md`

## Context

PLASMA 現階段以 **OpenOCD** 為燒錄軟體 Backend。Manufacturer DFP、Product Search 和 OpenOCD target/flash driver 的覆蓋範圍不同。Microchip Research 已保存 24,051 筆不重複、具來源連結的 *候選* ICPN；這不是經獨立核定的 Microchip 全部可訂購 SKU，更不是 PLASMA 已具備燒錄能力的數量。

Socket、Adapter、PPU 與 Site 等實體硬體測試需購置特定封裝的樣品與治具。若把 Socket HIL PASS 當作 Catalog 顯示條件，便會錯誤排除 OpenOCD 已支援、只是尚未備齊實體測試條件的 IC。反過來，若將所有 DFP 或 OpenOCD CFG 文字命中的 IC 直接列為 Supported，也會虛報實際軟體能力。

目前 Production Identity Catalog 的 admission contract 允許 `no_mapping`；IC Selector 也可呈現已收錄但尚未映射的 exact ICPN。Owner 於 2026-10-15 決議：**Selector visibility 不以 Phase 2 `SUPPORTED` 為門檻**。只要 Exact ICPN 已通過 Phase 1 `IDENTIFIED`，就應可被查詢並顯示其 Phase 1／2／3 狀態；真正的燒錄執行仍由 Phase 2、Runtime、電氣與安全 gate fail-closed。

## Decision

> **PLASMA Catalog／IC Selector 以 Phase 1 `IDENTIFIED` 的精確原廠 ICPN 為可見性門檻，並分別顯示 Phase 1 IC Information、Phase 2 Programming、Phase 3 PLASMA Compatibility 狀態。Selector 可見不等於可燒錄；Job／Batch 執行權限必須由 Phase 2 `SUPPORTED`、已安裝 Runtime、電氣／安全條件與必要的 Phase 3 配置 gate 獨立決定。**

具體規則：

1. **Manufacturer Research Catalog** 保存原廠發現的候選 ICPN、DFP 裝置名稱、搜尋失敗、生命週期觀測與證據；不受 OpenOCD 支援與否限制。只有通過 Phase 1 Exact ICPN identity gate 的 `IDENTIFIED` 記錄才取得 Selector visibility；`RESEARCH_ONLY`／`IDENTITY_DISPUTED` 不得冒充正式料號。
2. **Canonical Phase 1 Identity / Information Store** 管理精確原廠商業 ICPN 與逐欄位可驗證來源。不同 Brand 可使用不同官方取得介面，但進入 PLASMA 後必須收斂成同一份 Phase 1 schema、field-state 與 provenance contract；不得因 Brand 改變證據門檻。
3. **User-facing PLASMA Catalog / IC Selector View**（包括 `GET /api/devices/search`、`catalog_size`、`total_count`、分頁、IC Selector 與 picker）以 **Phase 1 `IDENTIFIED` exact ICPN** 為可見集合。Phase 2 `UNKNOWN／CANDIDATE／SUPPORTED／UNSUPPORTED` 與 Phase 3 `NOT_TESTED／PASSED／FAILED` 是顯示狀態，不是 Selector visibility filter。
4. 軟體支援資格要鎖定 **OpenOCD Provider / 版本或 source commit、Target／Device 對應、Flash Driver、必要的 Flash geometry／bank 假設以及 program、必要 erase、read/verify 等實際宣告的 operation 能力**，保留證據與約束。只有 CFG 檔案名稱、家族字首、確定性 `mapped` 路徑或研究候選，**不足以單獨宣告 OpenOCD = SUPPORTED**。不能在無實體的條件下證成必要晶片特性時，維持 Candidate/Unknown。
5. **硬體驗證獨立維度**：分開保存 IC/package、Socket／Adapter 型號與修訂版、PPU/Site 型號、供電與接腳映射、Programming Provider／PLASMA 軟體版本及測試結果。Phase 3 尚未測試的 Exact ICPN 仍可顯示；UI 必須明示 `NOT_TESTED`，不能標成 Hardware Passed。
6. **執行授權仍分離**：Catalog／IC Selector 顯示永遠不直接授權燒錄。Job/Batch 必須至少確認 Phase 2 `SUPPORTED`、相符已安裝 Runtime、電壓／操作／安全條件，並在產品執行政策要求時確認對應 Phase 3 硬體配置，全部 fail-closed。
7. **OpenOCD 是目前 Phase 2 Provider，不是 Phase 1 visibility gate。** 未來 Vendor Backend / Plasma-native Backend 可透過版本化 Programming Qualification Provider contract 加入，不得修改 Phase 1 Exact ICPN identity 標準來取得特殊待遇。

## Implementation Phases — 三階段 IC Detail 與 Exact ICPN 驗收漏斗（已採納規範）

IC Detail 的三個區塊是**不同的證據產品**，形成唯一的「原廠身分 → 軟體燒錄資格 → 實機相容性」三階段模型。**現行 ADR 不再使用任何額外的數字型研究分級；所有正式狀態都必須歸屬 Phase 1／Phase 2／Phase 3。**

**專案層級狀態（保留原決議）：**Phase 1 原廠資訊基礎架構已建立；Owner 於 2026-10-15 核准啟動 Phase 2 Programming；Phase 3 仍延後。此狀態**不代表**資料庫內每一個 ICPN 都已個別完成 Phase 1 或 Phase 2。

| Phase | UI 區塊 | 個別 Exact ICPN 的進入／完成條件 | 不得推論 |
| --- | --- | --- | --- |
| **Phase 1 — IC Information** | **01 IC Information** | **`IDENTIFIED`**：任何 Brand 都必須由原廠官方料號、物料或 Ordering 證據明確確認**完整商用 Exact ICPN**，並保存 Base Device／Family 與來源關係。Package、Pin Count、Flash、RAM、Working VDD、I/O Supply、Analog Supply、Temperature、Core 等欄位可後續補強；**`INFORMATION_COMPLETE`** 是獨立的欄位品質里程碑，不是 Selector visibility 門檻。 | Phase 1 `IDENTIFIED` 允許 Catalog／IC Selector 顯示；但不代表某 CFG 適用、Phase 2 `SUPPORTED`、Job／Batch 可執行或 PPU 實機通過。 |
| **Phase 2 — Programming** | **02 Programming** | **Phase 1 的子集合**：對**精確 ICPN**依原廠 Programming Guide／Reference Manual／Datasheet 及鎖定版本 OpenOCD 驗證 Silicon ID/Revision、Target CFG/Include、Flash Driver、Bank/Geometry/Security 與宣告的 Erase／Program／Read／Verify 操作，完成可追溯的 Programming Profile。只有通過資格審核者為 `openocd_software_support=SUPPORTED`。 | 家族名稱、共用 Core、單獨 CFG 或 Driver 字串，都不足以取得軟體燒錄資格。 |
| **Phase 3 — PLASMA Compatibility** | **03 PLASMA Compatibility** | **Phase 2 的子集合**：至少有一組明確版本化的 **IC／Package＋PPU／Site＋Socket／Adapter**，通過供電、Pin Mapping、SWD／JTAG、保護與實機 HIL。 | 軟體 `SUPPORTED` 不等於 HIL PASS；Catalog 可見或曾做過 HIL，也不能免除當次 Job／Batch 的安全檢查。 |

### 三階段數量契約：統一以 Unique Exact ICPN 計算

在**同一廠商、同一研究庫 Snapshot 與相同 OpenOCD 軟體資格範圍**下：

- **Phase 1 `IDENTIFIED`**：已由原廠證實身分、可列入 Phase 1 的完整商用 Exact ICPN。
- **Phase 1 `INFORMATION_COMPLETE`**：Phase 1 `IDENTIFIED` 中必要 IC Information 欄位均通過證據驗收者；**獨立統計**。
- **Phase 2 `SUPPORTED`**：Phase 1 `IDENTIFIED` 中通過指定 Programming Provider／版本與宣告操作之軟體資格審核者。
- **Phase 3 `PASSED`**：Phase 2 `SUPPORTED` 中至少有**一組指定硬體配置**通過實機驗收的精確料號。

**強制不變量：Phase 3 `PASSED` ⊆ Phase 2 `SUPPORTED` ⊆ Phase 1 `IDENTIFIED`。** 三個 Phase 都以 Distinct Exact ICPN 計數；不能把 CFG 數、家族數、Programming Profile 數、Research 候選數或 HIL 測試次數混入分母。**通過 HIL 的配置組合數另計。**

Phase 2 若不符合、證據不足、在指定 Provider／版本不支援，或日後軟體資格失效，**只調整 Phase 2 狀態，必要時同步撤銷依賴它的 Phase 3 `PASSED`；Phase 1 `IDENTIFIED` 身分仍保留**，並記錄不符合原因、Provider 版本及原廠證據。Phase 3 失敗只撤銷該硬體配置的 PASS；唯有**原廠身分本身不成立**，才依獨立 Phase 1 身分修正流程處理。

### Phase 1 — CFG 反向發現入口與原廠權威資料來源

**OpenOCD CFG-first Reverse Discovery 是預設的「研究入口／選料策略」，不是 IC Information 的原廠規格證據。** 任何替代 Provider／版本應依既有政策獨立核准。

1. **由 Config 反推候選 Family／Base Device**：使用指定 OpenOCD 版本／Commit 的 `tcl/target/*.cfg`，遞迴展開 Tcl Include，解析 Target、Flash Bank 與實際 Flash Driver。記錄 Provider、版本、CFG、Driver、來源雜湊，以及映射是否明確／通用／部分成立。單看 CFG 檔名或 Family 前綴不能證明精確 IC 可燒錄。
2. **反查原廠完整料號**：由已辨識家族尋找原廠 Product、Package／Quality、Ordering Table、Datasheet 或官方 Parametric Export。把**該家族中原廠實際列出的各種封裝與商用後綴料號**逐一建檔。**Phase 1 不要求每一個封裝後綴都有獨立 OpenOCD CFG、Driver 或 Silicon ID 證據**；但不能拼湊不存在的料號、把 Product 標題的 Active 當成每個 Material 都 Active，或把只有 Family／DFP Alias 的紀錄冒充完整 ICPN。
3. **`IDENTIFIED` 最低門檻**：`manufacturer`、**完整商用 `icpn`**、由原廠確認的 Base／Family 對應、官方 Source URI、來源證據作用範圍（Material／Ordering 與 Family／Product 必須分清）、觀察時間與身分證據狀態。同一完整商用身分去重；Lifecycle 與材料後綴分開記錄。猜測、模糊命中、衝突或不完整料號保持 `RESEARCH_ONLY`／`IDENTITY_DISPUTED`，**不得標為 Phase 1 `IDENTIFIED`**。
4. **原始證據封存與 Phase 1 數量分開管理**：能取得時封存原廠 XLSX／PDF／HTML／API 原始 Bytes 與 SHA-256。若無法封存，必須標記 `SOURCE_BYTES_NOT_ARCHIVED`，保留官方 URL、觀察時間、Source Scope，**不可聲稱已保存原廠 Binary SHA 或完整的原始檔位元重播**。但是可由官方**個別物料紀錄直接確認且無歧義**的 ICPN，仍可計為 `IDENTIFIED`；未封存來源須另列缺口。Phase 1 `IDENTIFIED` 決定 Selector visibility，但**不構成 Phase 2 燒錄資格或執行授權**。
5. **欄位持續補強，不阻擋 `IDENTIFIED`**：補齊 `base_device / package / pin_count / flash / ram / working_vdd / io_supply / vdda_or_analog_supply / temperature`，以及適用的 Core／Architecture。保留原始單位、工作模式、文件版次／表格、Exact／Family 適用範圍與 `VERIFIED／PARTIAL／UNKNOWN／CONFLICT`。如原廠明確證明沒有某個獨立電源軌，可使用附證據的 `NOT_APPLICABLE`；不得以 Absolute Maximum Ratings 當 Working VDD，亦不可將 VREF 混為 VDDA。
6. **`INFORMATION_COMPLETE` 門檻**：所有適用的必要欄位均有精確料號或明確涵蓋該料號的 Family 官方證據，結果為 `VERIFIED` 或有來源的 `NOT_APPLICABLE`。必要欄位存在 `UNKNOWN／PARTIAL／CONFLICT` 時不得列為資訊完整，**但不撤銷 Phase 1 `IDENTIFIED`**。來源原檔封存覆蓋率再單獨呈現。
7. **Phase 邊界**：Phase 1 不宣稱 Erase／Program／Verify 可用、不授權 `SUPPORTED`、不建立已驗證 Programming Profile，也不授權 Job／Batch 或實機 HIL。通過 Phase 1 `IDENTIFIED` 的 Exact ICPN 應可由 Catalog／IC Selector 查詢並顯示真實 Phase 2／3 狀態；尚未達 `IDENTIFIED` 的 Research-only 候選不得混入。

**案例：** 從 `lpc8xx.cfg` 發現家族後，可反查 NXP 官方 LPC811／812／822／824 各自存在的完整商用後綴。每一筆**經原廠個別確認**者即可進入 Phase 1 `IDENTIFIED`；即使某個 Silicon Revision 尚無 `lpc2000.c` 支援證據，也是在 Phase 2 再檢查。**一個 CFG 不等於一個 ICPN，也不代表整個家族已 `SUPPORTED`。**

**Phase 1 驗收輸出：** Phase 1 `IDENTIFIED` Exact ICPN 清單、官方來源與取得時間、Family／Ordering Variant Crosswalk、OpenOCD 研究入口、逐欄位覆蓋率、身分衝突、原始證據封存缺口、可重播的來源檢查，以及獨立的 `INFORMATION_COMPLETE` 數量。**不得藉此修改 Phase 2／3 結果或 Job／Batch 執行權限。**

### Phase 1 — Cross-vendor canonical discovery method

ST、NXP、Microchip 及未來 Brand 必須使用**同一套 discovery 判定流程與 canonical output**。差異只允許存在於原廠資料取得 adapter，不允許存在於 Phase 定義、欄位狀態、證據門檻或 Selector／execution 語意。

固定流程：

1. **Capability Seed**：從鎖定 Programming Provider（目前為 OpenOCD）的 Target／Include／Flash Driver／Silicon Probe Rule 建立技術研究入口；只記錄實際 evidence 與缺口，不建立另一套數字型研究狀態。
2. **Official Manufacturer Identity Acquisition**：回到原廠官方 Material／Ordering／Product／Parametric／DFP／Datasheet 等來源取得 Exact ICPN；不得用 CFG、家族名稱或後綴規則創造商用料號。
3. **Exact ICPN Crosswalk**：明確保存 `manufacturer + exact_icpn + base_device/family + source_scope`。只有無歧義官方完整商用料號可標為 Phase 1 `IDENTIFIED`。
4. **IC Information Projection**：Package、Pin Count、Flash、RAM、Working VDD、I/O Supply、VDDA、Temperature 等欄位各自使用 `VERIFIED／PARTIAL／UNKNOWN／CONFLICT／NOT_APPLICABLE`；未知不得補零、不得跨 rail 複製、Family evidence 不得假裝 Exact evidence。
5. **Programming Handoff**：Phase 1 `IDENTIFIED` 可進 Phase 2 review；只有經版本鎖定 Programming Provider + 原廠 programming evidence 完成 Exact ICPN qualification 才可標 `SUPPORTED`。
6. **Selector / Execution Separation**：Phase 1 `IDENTIFIED` 決定是否可搜尋；Phase 2、Phase 3 只決定顯示的能力狀態與執行 gate，不得反向刪除有效的 Phase 1 身分。

**本 ADR-0002 是此跨廠牌 discovery 方法的唯一規範來源。** 新的 ST／NXP／Microchip 或其他 Brand discovery 工作、review 與 consumer 都必須直接遵守本節的 Phase／field naming、證據門檻與 selector/execution 邊界；既有 vendor-specific historical artifacts 可以保留作證據與重播，但不得自行定義另一套 Phase 或 visibility policy。

### Vendor-specific official source adapters

不同原廠的官方介面可以不同，例如 ST Product Selector/eStore、NXP Material/Buy-Parametrics、Microchip MCP/DFP/Parametric Chart。這些都只是 **source adapter**；輸出必須遵守上述共同 contract。

### Phase 1 — official manufacturer bulk information acquisition — Microchip source-adapter example

**Decision / implementation method:** Use the manufacturer's **Parametric Search chart export → official MCP exact-ordering crosswalk → targeted datasheet evidence** as the default Microchip Phase 1 acquisition pipeline. This is an **approved workflow contract**, not a statement that a chart exporter, unattended scraper, or all-Microchip complete ingestion already exists. Other manufacturers may use equivalent official, source-bound bulk exports under the same field-level contract.

| Evidence layer | Acquisition and role | Evidence limitation |
| --- | --- | --- |
| **A. Parametric Search / XLSX (bulk)** | Navigate the official Microchip product category/MCU subcategory chart; use **Download Chart → All Data** to export the chart's products **and columns** as XLSX; retain the original file and chart URL/category. Manufacturer guide: [DS00004852A](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/MarketCommunication/Promotions/Parametric-Search-User-Guide-00004852.pdf), “Download Chart Button”; [current online guide](https://www.microchip.com/en-us/products/selection-tools/parametric-search-landing-page/user-guide). | **All Data is chart-scoped**, not all Microchip exact commercial ordering codes or all lifecycle states. A chart row can represent a base device rather than an orderable SKU; available columns vary by chart. A successful file export is a source capture, not automatic per-ICPN verification. |
| **B. Microchip official MCP (exact-ordering evidence)** | Query the [official Microchip MCP product server](https://www.microchip.com/en-us/resources/model-context-protocol-server) via documented Streamable HTTP endpoint `https://api.microchip.com/mcp/resources`, using bounded `search_products` queries and checked pagination; archive original requests/responses. Extract exact `partNumber`, source-provided `basePartNumber`, package/lead count and other actually returned fields. | Search is **not a proven complete enumeration API**. Related/fuzzy hits, vendor base aliases, missing/ambiguous results, or `NOT_FOUND` do not establish full SKU coverage, EOL, or silicon compatibility; fields absent from a response remain unknown. |
| **C. Manufacturer datasheet / ordering table (targeted gaps)** | For absent or conflicting fields, obtain the official versioned family/device document and bind **revision + exact ordering table / electrical table + page or section + applicability** to each finding. In particular distinguish working VDD, `VDDIO`, `VDDA`/`VDDANA` and internal rails such as `VDDCORE`. | Family electrical specs require exact-variant applicability checks; a family table alone stays `PARTIAL`. Only a source explicitly applying a field to an exact ICPN can justify `VERIFIED` for that field. Do not retrieve Programming Guide/Flash-controller semantics in Phase 1. |

**Execution sequence (source-first, repeatable, fail closed):**

1. **Select bounded cohort and chart:** prioritize families for which a pinned Programming Provider route or strong manufacturer demand already gives a concrete research reason, starting from the two existing ATSAMD21G18A pilot order codes. Record manufacturer, chart URL/ID, category/subcategory, selection/view settings, export scope, acquisition time and any manufacturer-published source revision/date **separately**. A manual XLSX export is acceptable as an initial capture; no undocumented export API or bypass of HTTP 403 is assumed or authorized.
2. **Archive original bytes before parsing:** store the unmodified XLSX/PDF/MCP response bytes and SHA-256 (and capture manifest containing URL, timestamp, media type, file size, chart/document identifier, acquisition outcome and licensing/access limitations). Verify hashes in an independent offline replay. Temporary CI artifacts with expiration are **not** permanent source archives; unavailable sources record explicit blockers rather than invented hashes.
3. **Normalize chart fields without fabricating evidence:** preserve the exact raw column name, raw value, original units, chart scope and provenance per field. Map only observed data into `manufacturer/icpn/base_device/package/pin_count/flash/ram/vdd/io_supply/vdda/temperature` and optional `core_architecture/core_model`; keep unmatched columns and nulls. Never silently coerce `UNKNOWN` to 0, treat KB as KiB, or apply a base-device number to every commercial suffix.
4. **Crosswalk commercial ICPNs:** use separately archived, bounded MCP query/pagination results and official exact ordering-code tables to build **`exact ICPN ↔ manufacturer-reported base device ↔ chart family row`** links. Deduplicate on complete original commercial order code; quarantine fuzzy matches and conflicting identities. Only exact-source rows may substantiate exact package, pin and temperature fields. A chart-only family value may be useful `PARTIAL` evidence but cannot be auto-upgraded to exact `VERIFIED`.
5. **Resolve missing supply fields selectively:** inspect the official datasheet's *power-supply and operating conditions* material only when the chart/MCP omits or contradicts a Phase 1 information field. Retain distinct rail names, mode/temperature/voltage conditions and any restrictions on multiple supplies; leave unjustified `io_supply` or `vdda` as `UNKNOWN` or `PARTIAL`, not copies of `vdd`.
6. **Reconcile independently:** attach a source locator, original record/cell or document table, version and original-byte reference to **each** field. Track `VERIFIED / PARTIAL / UNKNOWN / CONFLICT` separately; preserve conflicting observations without winner-by-precedence. No automatic Research→internal `ADMITTED`, Production, software `SUPPORTED`, public selector or physical readiness promotion.
7. **Emit auditable Phase 1 deliverables:** create source manifest/immutable raw-source references, a normalized exact-ICPN research ledger, exact-vs-family evidence crosswalk, per-field coverage and conflict report, and deterministic offline replay/negative tests. Report denominators **per chart/category, observed base devices, observed exact ordering codes, independently admitted identities**, and missing/unresolved rows separately; never interpret a chart or MCP search count as Microchip-wide SKU coverage.

**Acceptance / stop gates:** Test an original-byte replay; reject SHA/version mismatch, duplicate/ambiguous exact order codes, family→exact `VERIFIED` promotion, missing units/source locator, false completeness claims and any Production/Phase 2/3 write. If chart export, MCP capture or datasheet access fails, preserve `SOURCE_NOT_AVAILABLE`/coverage gaps and stop that lane or retry only by a permitted official mechanism. Completion is a **reviewable Phase 1 information cohort with quantified coverage**, not a programming qualification; subsequent cohorts and any identity admission remain separately reviewed. The existing Microchip Research inventory (24,051 source-linked candidates) is **not** automatically bulk-enriched or admitted by this decision.

### Phase 2 — Programming implementation contract（依原廠程式文件做軟體資格篩選）

Phase 2 從 **Phase 1 `IDENTIFIED` 的 Exact ICPN 集合**選取候選。逐一核對原廠 Programming Guide／Reference Manual／Datasheet 與指定 Programming Provider／版本，確認實際 Silicon ID／Revision、Target/Driver/Flash Bank、ROM IAP 或 Flash Controller、Geometry、Security、Reset/Clock 條件，及宣告的 **Erase／Program／Read／Verify** 操作，建立有版本與適用範圍的可重用 Programming Profile。

- **`SUPPORTED`**：精確 ICPN 的軟體燒錄適用性與宣告操作有足夠、可重播的版本鎖定證據；不宣稱 PPU／Socket HIL。
- **`CANDIDATE／UNKNOWN／BLOCKED`**：只有部分 Programming Provider 線索，或必要文件／證據不足、相互衝突；Phase 1 `IDENTIFIED` 身分仍保留，但 Phase 2 不得標為 `SUPPORTED`。
- **`UNSUPPORTED`（限定版本與操作範圍）**：經審核確定該 Provider／版本／操作不適用；保留 Phase 1 `IDENTIFIED` 身分，不可推論全世界任何後端都永遠無法燒錄。
- **退版或資格回歸**：保留原廠料號與歷史證據，撤銷受影響的 Phase 2 `SUPPORTED`，並重新評估依賴它的 Phase 3 `PASSED`。

Phase 2 可以建立獨立的軟體資格權威並投影到同一 IC Selector。Phase 1 `IDENTIFIED` 即可被搜尋與檢視；在尚未取得 Phase 2 `SUPPORTED` 前，UI 必須清楚顯示 `UNKNOWN／CANDIDATE／UNSUPPORTED`，且 Job／Batch 不得把 Selector 可見性解讀為可燒錄授權。

### Phase 3 — PLASMA Compatibility handoff（與軟體資格分離的實機相容性）

Phase 3 僅能對 Phase 2 `SUPPORTED` 的 Exact ICPN 建立**特定配置實機驗證**。驗收證據需鎖定 Device／Package、Socket／Adapter 型號及 Revision、PPU／Site、Pin Mapping、電壓／電流／保護、Debug Interface、PS／PL／Programming Provider 版本及實際 HIL 操作。

Phase 3 `PASSED` 統計**唯一 Exact ICPN 數**；通過的實體配置或測試次數另外統計。Phase 2 `SUPPORTED` 而 Socket／PPU `NOT_TESTED` 的 IC 仍可在 Selector 顯示其真實狀態，但不得標示 Phase 3 `PASSED`。Job／Batch 對選定 Site 的執行期、安全及供電條件維持 Fail Closed；不得用 Phase 1／2 文件捏造 HIL PASS。

### Visibility and execution boundary

The IC Selector is a **status surface**, not an execution entitlement surface. Phase 1 `IDENTIFIED` Exact ICPNs are searchable and visible regardless of Phase 2/3 result. The same row must expose Phase 1 IC Information quality, Phase 2 Programming state and Phase 3 PLASMA Compatibility state independently. No existing `OpenOCD CFG exists` badge, Phase 1 identity, Production admission or Selector visibility may be interpreted as affirmative programming qualification. Job／Batch remains fail-closed on Phase 2 `SUPPORTED`, installed Runtime and required electrical／hardware safety gates.

## Phase scope of the existing OpenOCD-first and Core/Driver requirements

OpenOCD-first CFG／Target／Driver 分析是**Phase 1 的預設研究入口**，同時為**Phase 2 的燒錄資格**提供技術證據。Phase 1 的身分權威來源仍是原廠完整商用料號；Phase 2 才判定精確 Silicon／Programming Operation 相容性；Phase 3 才判定指定硬體配置的實機 HIL。現行流程不再維護另一套研究優先級 enum。

目前整體專案狀態仍為：Phase 1 架構已建立、Phase 2 Programming 已核准執行、Phase 3 延後。專案階段進度**不代表**每顆 Exact ICPN 均已個別通過。舊研究資料、來源 Hash 與未完成的欄位／資格缺口均保留，不得因本次修訂而回溯視為 `IDENTIFIED`、`INFORMATION_COMPLETE` 或 `SUPPORTED`。



## Cross-vendor discovery execution order

ST、NXP、Microchip 與未來 Brand 一律使用相同的 discovery 執行順序；差異只允許存在於原廠資料取得介面。

1. **鎖定 Programming Provider 與版本**：使用 `release/openocd.json` 或另行核准的 Provider Registry，保存 Provider、Version／Source Commit、Target CFG、Include Graph、Flash Driver、Silicon Identity／Probe Rule 與內容雜湊。
2. **由軟體能力反查原廠裝置範圍**：Capability Seed 只能建立技術研究入口，不能建立商用料號、Phase 1 身分或 Phase 2 支援結論。
3. **只由原廠官方來源取得 Exact ICPN**：使用各 Brand 官方 Material／Ordering／Product／Parametric／DFP／Datasheet 等來源，保存 Source URI、Scope、Observation Time 與可取得的原始 Bytes／Hash。不得依 CFG 名稱、Family 前綴或 suffix grammar 創造不存在的料號。
4. **Phase 1 判定**：只有原廠完整商用 Exact ICPN 身分無歧義者可標為 `IDENTIFIED`。IC Information 各欄獨立使用 `VERIFIED／PARTIAL／UNKNOWN／CONFLICT／NOT_APPLICABLE`，不得用預設值填補未知。
5. **Phase 2 判定**：只有 Phase 1 `IDENTIFIED` 的 Exact ICPN 可進 Programming review；必須完成版本鎖定 Provider、原廠 programming evidence、Silicon／Revision、Flash geometry／security 與宣告操作的適用性驗證，才可標為 `SUPPORTED`。
6. **Phase 3 判定**：只有 Phase 2 `SUPPORTED` 的 Exact ICPN 可建立指定 PPU／Site／Socket／Adapter 配置的實機驗證；通過者標為 `PASSED`。
7. **停止與重啟規則**：證據不足就保留當前 Phase 的真實狀態與 missing-evidence 清單並停止擴張；只有 Provider 版本、原廠證據或核准產品需求發生實質變化時才重新開案。缺證據不能推論成永久不支援。
8. **跨 Brand 一致性**：相同證據強度必須得到相同 Phase 判定；不得因 ST、NXP、Microchip 或任何 Brand 使用不同網站／API 就放寬 identity、field、programming 或 HIL 證據門檻。

**本 ADR-0002 是上述 discovery 方法的唯一規範來源。** 歷史研究 artifact 可保留原始舊名詞以維持可追溯性，但新資料、API、UI、報表、CI 與 workflow 不得再建立或依賴另一套數字型研究狀態。

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
- 對具有 source-backed Target／Driver 路徑的族群，仍須個別確認 Flash driver 操作、晶片識別／revision、bank/base/geometry、所需 transport、目標限制以及 Exact ICPN 映射；若任一關鍵證據不足，Phase 2 維持 `CANDIDATE`／`UNKNOWN`，不宣稱 `SUPPORTED`。
- JTAG 不限 ARM；Microchip PIC32MX/MIPS 與部分 AVR JTAG 是非 ARM 路線的優先檢查範例。SWD 對 Cortex-M 特別常見，但不得假設所有 ARM MCU 都可由 PLASMA 所選 OpenOCD Flash Driver 燒錄。
- 不建立額外的研究優先級 enum。Phase 2 只使用 `UNKNOWN／CANDIDATE／SUPPORTED／UNSUPPORTED`；研究排程可依業務需求與 evidence gap 決定，但不得寫入另一套產品狀態。

### 3. Core-aware Coverage Metrics

報表最少以 `manufacturer × core_architecture/core_model × debug_transport × provider_version × flash_driver` 分組，並**明確分開不同母體與顆粒度**：

1. 原廠 Research 候選身分數（DFP 名稱或精確 ICPN 需分開；未完成商業身分校驗者不可混入精確 ICPN 總數）。
2. OpenOCD Target／Driver source-backed **Device/Profile** 數量（不是精確 ICPN 數）。
3. 已完成 OpenOCD 軟體 `SUPPORTED` 的 **精確 ICPN** 數量與預設 PLASMA Catalog 可見數。
4. 已完成特定 Socket／PPU／Site Configuration HIL 的數量（不是軟體支援 ICPN 數）。
5. Phase 2 的 `CANDIDATE`、`UNKNOWN`、`UNSUPPORTED` 分別統計；Research backlog／archive 另計工作量，不能把 backlog 類別變成 Phase 狀態，也不能以 0 代替未知。

若要驗證「OpenOCD 支援的 IC 以 ARM 為多數」，必須先固定 **Provider／版本、Microchip 或跨廠範圍、統計單位（Target、Device/Profile、精確 ICPN）和母體**，再計算各 Core 比例；不允許以 Target Config 檔案數、Research 24,051 候選數或對 Cortex-M 生態的直覺直接宣稱多數。未知／未分類的比例必須揭露。

**Migration boundary:** 此節為已批准的架構實作要求，**不是目前 Catalog API、IC Support Schema 或 Microchip ICPN 資格審核已完成的聲明**。不得藉此更新 Production ICPN 或變更 Job/Batch 安全驗證；實作仍需單獨 PR／CI／Owner Merge Gate。

## Status dimensions

建議的邏輯維度如下（**為政策模型，並非宣稱現行 API 已有同名欄位**）：

| Phase 2 state | Programming qualification | IC Selector visibility（Phase 1 已 `IDENTIFIED`） |
|---|---|---|
| `UNKNOWN` | 尚無足夠 Programming 證據 | **顯示**，明示尚未完成 Phase 2 |
| `CANDIDATE` | 部分 Target／Driver／Silicon 線索，尚未達可證明燒錄條件 | **顯示**，明示 Candidate |
| `SUPPORTED` | 版本鎖定、Exact ICPN 對應、Flash 操作範圍及來源證據達成軟體支援審查 | **顯示**，明示 Supported |
| `UNSUPPORTED` | 已審查所指定 Provider／版本／操作不支援 | **顯示**，明示 Unsupported |

硬體可以另行記錄 `NOT_TESTED`、`READY`、`PASSED`、`FAILED`，但實際上 **Socket / Adapter / PPU / Site 應是不同的、有版本與 Configuration identity 的證據**，不應用單一扁平狀態掩蓋設備和治具差異。

範例：`openocd_software_support=SUPPORTED` 且 `socket_validation=NOT_TESTED`，IC 可以被搜尋與選取；是否能對某座 Site 執行燒錄，由執行階段另行判定，不應自動允許寫入。

## Migration gap and ownership

- **Accepted now:** 跨 Brand Phase 1／2／3 定義、Phase 1 `IDENTIFIED` Selector visibility、Phase 2／3 與 execution 的獨立 fail-closed 邊界。
- **Not yet fully normalized:** ST／NXP／Microchip 的歷史資料仍分散於不同 artifact／resolver；後續 migration 要把它們投影成相同 Phase 欄位與 UI payload，而不是再建立 Brand-specific policy。
- 現行 `docs/architecture/icpn-catalog-admission-policy.json` 的 `requires_deterministic_backend_route_or_explicit_mapping_state`，是內部 **identity admission** 契約，**不得被誤讀為 Public Catalog 可見規則**。
- 現行 `backend.mapping_status=mapped` 主要表示確定性路由，尚不能概括為已做所有 software qualification；`no_mapping` 更不能當 Supported。Research `backend_candidate` 不可轉為可執行路由。
- 保留既有 Production exact ICPN 資料與研究證據，不透過本 ADR 刪除或大規模匯入 Production rows。
- 後續實作由 [Issue #849](https://github.com/physicslu/plasma/issues/849) 追蹤，須分開審查 source/version qualification、Product API／UI 及 execution gate regression。ST、NXP、Microchip 使用**同一套政策**；不得對不同廠商放寬。

## Validation / acceptance

**後續實作 PR 必須新增的 Phase Funnel 契約測試：**

- 一份 OpenOCD CFG 可反查原廠家族內多個官方完整商用封裝／Ordering Variant；每筆原廠個別證實者可獨立成為 Phase 1 `IDENTIFIED`，不需每筆各有 CFG；**臆造後綴、只有 Product Title 的 Active** 都不得計入。
- 分別報告 Phase 1 `IDENTIFIED`、Phase 1 `INFORMATION_COMPLETE`、原檔已封存與僅觀察到原廠網頁的比例，以及逐欄位證據狀態；缺失的 VDDA 或原始 Binary 不得假裝 `VERIFIED`。
- Phase 2 證據不足、指定版本不支援時仍保留 Phase 1 `IDENTIFIED`；Phase 2 不得標為 `SUPPORTED`，Phase 3 不得標為 `PASSED`。不能只因 OpenOCD 不適用就刪除原廠有效料號。
- 三階段均以 **Distinct Exact ICPN** 統計，不得混入 CFG 檔數、Base Device、Family 頁數、Profile 數或 HIL 測試執行次數；每個 Snapshot 驗證 Phase 3 `PASSED` ⊆ Phase 2 `SUPPORTED` ⊆ Phase 1 `IDENTIFIED`。資訊完整數和實體配置組合數獨立報告。
- Phase 3 `PASSED` 必須有指定配置；Phase 2 `SUPPORTED` 但 Socket 未測的 IC 仍可顯示於 Selector，但 Phase 3 狀態必須維持 `NOT_TESTED`；單一硬體失敗不得直接撤銷 Phase 2。

1. 使用實際 Phase 1 `IDENTIFIED` canonical rows 計算 Selector／API 的結果總數、Vendor／Family counts，不手填或繼承歷史 coverage 數。
2. 測試 Phase 1 `IDENTIFIED` 但 `no_mapping`、僅 family-matched CFG、只有 candidate source、或尚無 Flash operation 證據的 Exact ICPN **仍可在 Selector 搜尋**，但 Phase 2 必須正確顯示 `UNKNOWN／CANDIDATE`，且 Job／Batch 不得執行。
3. 測試 Phase 2 `SUPPORTED` 但 Socket／PPU 未測試的 ICPN **仍顯示**，同時標記 Phase 3 `NOT_TESTED`。
4. API、UI、分頁、結果總數、Vendor／Family counts 使用同一個 Phase 1 `IDENTIFIED` 集合；Phase 2／3 只改變狀態欄位，不改變 Selector 是否看得到。
5. 保持 Job／Batch 的 runtime executable、選定 Site、電氣限制、配置安全與硬體審核獨立 fail-closed；嚴禁由 Catalog presence 推導可執行。
6. Research-only Microchip 24,051 候選與原廠資料庫不受顯示規則刪除或修改。
7. Core／Transport／Target／Flash Driver／Exact ICPN 每一層具可審核來源與版本，且測試同 Core 但不同 Flash Driver 不得被誤判可互換；多核心或未知 Core 不可被強制歸類為 ARM。
8. 測試 Cortex-M/SWD/CFG-only 仍只能形成 Phase 2 `CANDIDATE` 或 `UNKNOWN`，以及 MIPS/PIC32MX 或 AVR/JTAG 等**非 ARM**來源線索可依完全相同的證據門檻進行審核；source-backed 路徑不得自動晉升 `SUPPORTED`。
9. Core 統計顯式標明 Programming Provider 版本與 Target／Device/Profile／Exact ICPN 各自分母，並分別報告 Phase 1／2／3 狀態；不得以 Research 候選總數作為已支援分母，也不得未經統計就宣稱 ARM 占多數。

## Alternatives considered

- **所有 Research 候選都直接顯示**：拒絕；尚未通過 Phase 1 `IDENTIFIED` 的字串可能是 alias、family name、模糊命中或不存在的商用料號。
- **只顯示 Phase 2 `SUPPORTED`**：拒絕；會把有效 Phase 1 Exact ICPN 隱藏掉，使用者也無法看出 Programming 尚未完成。
- **只顯示 Phase 3 `PASSED`**：拒絕；把治具／硬體可取得性錯當成 IC identity 或軟體資格門檻。
- **Phase 1 `IDENTIFIED` 即可顯示，Phase 2／3 狀態獨立呈現，execution 另行 fail-closed**：**採用**。

## Decision summary

```text
Original manufacturer discovery/evidence → Research (retained)
       ↓ original manufacturer exact material identity gate
Canonical Phase 1 IDENTIFIED Exact ICPN store
       ↓ (independent of information-complete / software qualification)
User-facing PLASMA IC Selector / Catalog (all IDENTIFIED)
       ├── Phase 1 IC Information quality: VERIFIED / PARTIAL / UNKNOWN /
       │   CONFLICT / source-backed NOT_APPLICABLE
       ├── Phase 2 Programming state: UNKNOWN / CANDIDATE /
       │   SUPPORTED / UNSUPPORTED (versioned provider + operations)
       └── Phase 3 PLASMA Compatibility: NOT_TESTED / PASSED / FAILED
                     ↓ separate runtime execution entitlement
Job / Batch requires Phase 2 SUPPORTED + installed compatible Runtime
    + electrical/safety gates + selected-site hardware requirements
    → fail closed; Catalog or CFG presence is never authorization
```

**Normative clarification (2026-10-15):** The former summary diagram
placed software qualification *before* public Selector visibility and
labeled the Catalog `SUPPORTED only`. That diagram contradicted
the accepted Decision and Phase 1 visibility rules above, and is
superseded by this corrected summary. No brand (including Microchip)
may use CFG existence, historical priority partitions, information
completeness, or internal Production ingestion batches as an additional
Phase 1 identity qualification criterion. Original source custody and
deployment migration remain independently gated.
