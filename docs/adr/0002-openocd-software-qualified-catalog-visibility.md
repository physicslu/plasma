# ADR-0002: PLASMA IC Discovery、Catalog Level 與 Catalog 可見性統一政策

- **Status:** Accepted (cross-Manufacturer Catalog Level 0/1/2/3 policy; L0 Research / L1 Programming Candidate / L2 Selector / L3 Verified boundary approved 2026-10-16)
- **Date:** 2026-10-14
- **Scope:** Manufacturer Research / Canonical Device Registry / Programming Catalog & IC Selector / Programming Provider qualification / PPU-Site-Socket physical validation
- **Owner decision:** 2026-10-14; Catalog Level terminology revised 2026-10-16; Level 0 added and Level 0/1/2/3 boundaries approved 2026-10-16
- **Tracking:** [Issue #849 — Public Catalog qualification](https://github.com/physicslu/plasma/issues/849), [Issue #851 — OpenOCD-first manufacturer research prioritization](https://github.com/physicslu/plasma/issues/851)
- **Related:** `docs/architecture/icpn-catalog-admission-policy.json`, `data/device-catalog/production/README.md`, `docs/architecture/ic-selector.md`, `docs/architecture/device-support-validation.md`, `docs/architecture/openocd-versioned-provider-registry-v1.md`

## Context

PLASMA 現階段以 **OpenOCD** 為燒錄軟體 Backend。Manufacturer DFP、Product Search 和 OpenOCD target/flash driver 的覆蓋範圍不同。Microchip Research 已保存 24,051 筆不重複、具來源連結的 *候選* ICPN；這不是經獨立核定的 Microchip 全部可訂購 SKU，更不是 PLASMA 已具備燒錄能力的數量。

Socket、Adapter、PPU 與 Site 等實體硬體測試需購置特定封裝的樣品與治具。若把 Socket HIL PASS 當作 Catalog 顯示條件，便會錯誤排除 OpenOCD 已支援、只是尚未備齊實體測試條件的 IC。反過來，若將所有 DFP 或 OpenOCD CFG 文字命中的 IC 直接列為 Supported，也會虛報實際軟體能力。

2026-10-15 的舊決議曾讓 Exact ICPN identity 直接取得 IC Selector visibility。Owner 於 2026-10-16 修正為四級 Catalog maturity，並進一步決議產品表面分離：**Level 0 `DISCOVERED` 僅存在於 Internal Research Registry，不對一般 User 暴露；一般 Customer-facing IC Selector 顯示 Level 1／2／3，並提供 Catalog Level Filter；Job Picker 只允許 Level 2／3。** Level 1 代表有 source-backed programming route、可作為客戶委託 qualification 的候選，但不代表可燒錄。Level 2 仍不等於執行授權；真正燒錄必須另外通過 installed Runtime、route、電氣與安全 gate。

## Decision

> **PLASMA 將「原廠存在」、「有具體 programming route 值得 qualification」、「已可軟體燒錄」與「PLASMA 實機已驗證」分成四級：Level 0 `DISCOVERED` → Level 1 `PROGRAMMING_CANDIDATE` → Level 2 `PROGRAMMABLE` → Level 3 `PLASMA_VERIFIED`。一般 Customer-facing IC Selector 顯示 L1–L3；L0 僅供 Internal Research。Job Picker 只顯示 L2/L3。任何 Catalog Level 都不是 Job／Batch 執行授權；執行仍須獨立通過 Runtime、route、電氣與安全 gate。**

具體規則：

1. **Manufacturer Research Catalog** 保存原廠發現的候選 ICPN、DFP 裝置名稱、搜尋失敗、生命週期觀測與證據；不受 Programming Provider 支援與否限制。尚未能確認完整商用 Exact ICPN 的 alias／family／模糊候選不取得 Catalog Level。由原廠來源無歧義確認 Exact ICPN 後，至少可進 **Level 0 `DISCOVERED` Research Registry**；但 Level 0 不代表有任何可用 programming route，也不得進一般 IC Selector。
2. **Canonical Identity Store** 管理精確原廠商業 ICPN 與逐欄位可驗證來源，並作為 Level 0+ 的共同 identity authority。**Level 1 `PROGRAMMING_CANDIDATE` 不是身分層，而是 programming-relevance admission：必須在 Exact ICPN identity 已成立的前提下，另有至少一條 source-backed Programming Provider／target／driver／algorithm／ROM-IAP／官方 programming route，可合理映射到該 Exact ICPN 或其已證實 Base／Family。**
3. **Customer-facing IC Selector View** 收錄 **Level 1 `PROGRAMMING_CANDIDATE`、Level 2 `PROGRAMMABLE`、Level 3 `PLASMA_VERIFIED`**，並提供 Level Filter。Level 1 可被一般 User 搜尋與檢視，用來表達「已有具體 programming route、可委託 qualification」，但 `job_selectable=false`；只有 Level 2／3 可進 Job Picker。Level 0 僅存在於 Internal Research Registry，不由 public Selector API 暴露。
4. 軟體支援資格要鎖定 **OpenOCD Provider / 版本或 source commit、Target／Device 對應、Flash Driver、必要的 Flash geometry／bank 假設以及 program、必要 erase、read/verify 等實際宣告的 operation 能力**，保留證據與約束。只有 CFG 檔案名稱、家族字首、確定性 `mapped` 路徑或研究候選，**不足以單獨宣告 OpenOCD = SUPPORTED**。不能在無實體的條件下證成必要晶片特性時，維持 Candidate/Unknown。
5. **硬體驗證獨立維度**：分開保存 IC/package、Socket／Adapter 型號與修訂版、PPU/Site 型號、供電與接腳映射、Programming Provider／PLASMA 軟體版本及測試結果。Catalog Level 3 尚未測試的 Exact ICPN 仍可顯示；UI 必須明示 `NOT_TESTED`，不能標成 Hardware Passed。
6. **執行授權仍分離**：Programming Catalog／IC Selector 顯示永遠不直接授權燒錄。Job/Batch 必須至少確認導出 Catalog Level 2 的 `ProgrammingQualification.state == SUPPORTED` 仍適用、相符 Runtime 已安裝、route／電壓／操作／安全條件成立，並在產品執行政策要求時確認對應 Catalog Level 3 verified configuration，全部 fail-closed。
7. **OpenOCD 是目前主要 Programming Provider 之一，但不是 identity authority。** OpenOCD CFG／driver／target 可讓 Level 0 Exact ICPN 取得 Level 1 `PROGRAMMING_CANDIDATE` 的研究依據；只有版本鎖定 qualification 對 Exact ICPN 產生 `SUPPORTED`，才可導出 Level 2 `PROGRAMMABLE`。未來 Manufacturer backend / PLASMA-native backend 適用同一規則。


### Catalog Level 定義（唯一正式術語）

Catalog Level 描述的是**一顆 Exact ICPN 對 PLASMA programming 的成熟度**，不是專案時程，也不把「原廠身分存在」誤當成「PLASMA 已經值得支援」。正式產品語意使用四級：

| Catalog Level | 正式名稱 | 核心問題 | 達成條件 | 主要產品面 |
|---|---|---|---|---|
| **Level 0 — DISCOVERED** | **Research Inventory** | 這顆 Exact ICPN 是否確實存在，值得保留等待未來研究？ | Exact Manufacturer ICPN 身分及來源無歧義成立；**不要求**任何 Programming Provider／CFG／driver／algorithm 路徑 | **Internal Research Registry only；一般 User 不可見** |
| **Level 1 — PROGRAMMING_CANDIDATE** | **Programming Candidate** | PLASMA 是否已有具體、可稽核的 programming route 值得進一步 qualification？ | Level 0 + 至少一條 source-backed Provider／target／driver／algorithm／ROM-IAP／官方 programming route，且 applicability 可合理落到該 Exact ICPN／已證實 Base／Family | **Customer IC Selector + qualification/service-request candidate；不可直接建立 Job** |
| **Level 2 — PROGRAMMABLE** | **Programming Qualified** | PLASMA 是否已有合格軟體燒錄方法？ | Level 1 + 至少一個版本鎖定 Programming Provider 對該 Exact ICPN 的 `ProgrammingQualification.state == SUPPORTED` | Programming Catalog / Job IC Selector |
| **Level 3 — PLASMA_VERIFIED** | **PLASMA Compatibility Verified** | PLASMA 實機是否驗證過？ | Level 2 + 至少一組版本化 PPU／Site／Socket／Adapter／FPGA／PS／Provider configuration HIL `PASSED` | Verified badge / verified configuration selection |

**Identity status 與 Catalog Level 分離。** 完整商用 Exact ICPN 身分成立是進入 Level 0 的最低條件；`INFORMATION_COMPLETE` 仍是欄位品質，不是升級條件。alias、family name、DFP device name、模糊或衝突的料號仍留在 pre-Level Research domain，不得算 Level 0。

**Level 1 是 programming relevance gate，不是 support claim。** CFG 名稱、family prefix 或 driver 線索可以成為 Level 1 證據的一部分，但必須 source-backed 且能說明與 Exact ICPN／Base／Family 的 applicability。Level 1 可出現在一般 IC Selector，供 User 看見「PLASMA 已找到可研究的 programming route」，但必須明示 `PROGRAMMING_CANDIDATE`、不得宣稱可燒錄、不得由 Job Picker 選取。

**正式不變量：**

```text
Level 3 PLASMA_VERIFIED ⊆ Level 2 PROGRAMMABLE ⊆ Level 1 PROGRAMMING_CANDIDATE ⊆ Level 0 DISCOVERED
```

**Microchip 典型案例：** 原廠已確認、但目前沒有 OpenOCD 或其他 Provider programming route 的大量 Exact ICPN 應停在 Level 0。它們保留在 **Internal Research Registry**，未來有新 Provider、CFG、driver、algorithm 或官方 programming path 時可升到 Level 1；在升到 Level 1 前不得由 public IC Selector API 暴露。

**舊術語 migration：** Active schema／API／runtime payload **不得保留** `phase1_*`／`phase2_*`／`phase3_*` 欄位，也不得提供 compatibility alias。Source-locked historical artifact 的原始 bytes、歷史檔名或內部欄位可以原樣保存作 forensic input，但 canonical parser 必須轉成 Catalog Level／Programming Qualification 欄位後才可進 Product domain。

### Cross-Manufacturer canonical production boundary（規範性）

本 ADR 正式使用 **Manufacturer** 表示 IC 原廠。ST、NXP、Microchip 僅是 PLASMA 現階段已研究的 Manufacturer 實例，**不是架構上的固定集合、enum 或 hard-coded allowlist**；未來新增任何 Manufacturer 時，必須直接適用相同 contract。

PLASMA 採用下列唯一資料流：

```text
Manufacturer-specific Research / Discovery
        ↓
Common Catalog Level 0 / 1 / 2 / 3 Qualification Gates
        ↓
Manufacturer-neutral Canonical PLASMA Data Model
        ↓
Canonical Device Registry + Programming Catalog / API / IC Selector UI
```

1. **Research / Discovery 可以 Manufacturer-specific。** 各 Manufacturer 可依其官方介面使用不同 Product API、Web、Parametric Export、DFP、Datasheet、Ordering Table、Programming Guide、OpenOCD reverse discovery 或其他可稽核來源；Research artifact、crawler、adapter 與暫存 schema 不要求一致。
2. **Qualification 是 Research 與 Product domain 的唯一邊界。** Research candidate 不得直接成為 Product row。資料只有在符合本 ADR 的 Catalog Level 0／1／2／3 gate 後，才能投影至對應的 Canonical Production state。
3. **通過 gate 後不得再建立 Manufacturer-specific Product schema。** Canonical identity 使用 `(manufacturer, exact_icpn)` 作為邏輯唯一鍵；所有 Manufacturer 共用相同 Catalog Level 定義、field-state、provenance、Programming Qualification 與 Compatibility contract。
4. **Catalog Level store 可以分離，identity 必須共用。** Catalog Level 0、Catalog Level 1、Catalog Level 2、Catalog Level 3 可因 lifecycle、版本化與 evidence 特性採不同實體 Store／Repository，但必須引用同一 Canonical Identity。此 ADR 所稱「共用資料」指 **Common Canonical Data Model + Common Repository / Service Boundary**，不要求所有 evidence 塞入單一資料表。
5. **Product API 必須是共用 contract。** Device Registry 與 Programming Catalog 可採不同 projection／endpoint，但都必須引用同一 canonical identity + Catalog Level contract；不得新增 `/api/st/*`、`/api/nxp/*`、`/api/microchip/*` 等 Manufacturer-specific Product API 來繞過共同模型。現有 `GET /api/devices/search` 的 Level 1 visibility 行為列為 migration debt。
6. **Product payload 不得暴露舊 Phase schema。** `phase1_*`／`phase2_*`／`phase3_*` active 欄位與 compatibility alias 一律移除。Manufacturer-specific payload（例如既有 NXP profile）仍是後續 canonical normalization debt，但不得以 Phase 命名重新包裝。Microchip active payload改用 `microchip_ic_information`，不再提供 `microchip_phase1_ic_information`。
7. **UI 只理解 canonical Catalog Level contract。** IC Selector／IC Detail 可以顯示 Manufacturer 名稱與 Manufacturer-specific evidence，但不得以 ST／NXP／Microchip 分支決定 Catalog Level semantics、Selector visibility 或 execution entitlement。
8. **Programming Provider 與 Manufacturer 都不是 Product schema。** OpenOCD、未來 Manufacturer backend 或 PLASMA-native backend 都只能作為版本化 Catalog Level 2 Provider；Provider-specific evidence 必須 normalize 成共用 `ProgrammingQualification`。
9. **Migration 不得改寫已核准 evidence。** Manufacturer-specific historical artifact 可以保留供 forensic replay；後續 migration 只改 canonical projection／API boundary，不得因 schema normalization 自動晉升或降級任何 ICPN 的 Catalog Level 狀態。

**架構不變量：**

```text
Manufacturer-specific Research
    → Common Qualification Gates
    → Manufacturer-neutral Canonical Production Data

Catalog Level 3 PLASMA_VERIFIED ⊆ Catalog Level 2 PROGRAMMABLE ⊆ Catalog Level 1 PROGRAMMING_CANDIDATE ⊆ Catalog Level 0 DISCOVERED
```

任何新 Manufacturer 的 onboarding 都只能新增／修改 Research source adapter、evidence parser 或 provider implementation；**不得要求新增一套 Manufacturer-specific Product policy、Catalog Level enum、Product API 或 UI qualification branch。**

### Cross-Manufacturer Promotion Framework（規範性）

Catalog Level 的 authority 仍是 canonical `ProgrammingQualificationRegistry`；coverage/reporting 層**不得自行升降級**。Cross-Manufacturer Promotion Framework 只讀 canonical qualification 結果，負責兩件事：按 Manufacturer 對帳 L0/L1/L2/L3 數量，以及用同一套 blocker vocabulary 說明每顆 Exact ICPN 下一個 promotion edge 為何尚未通過。

Canonical promotion evidence class 先將不同 Manufacturer／Provider 的來源正規化成共同語意：

| Evidence class | 意義 |
|---|---|
| `IDENTITY_ONLY` | 只有 canonical Exact ICPN identity；沒有已 admitted programming route |
| `CATALOG_MAPPED_ROUTE` | Canonical Catalog 已有 mapped target route |
| `BACKEND_CANDIDATE_ROUTE` | 已有 source-backed backend candidate，但仍是 research-only |
| `REVIEWED_PROGRAMMING_PROVIDER` | 已進入版本化 Programming Provider review／qualification |
| `PLASMA_VERIFIED_CONFIGURATION` | 已有版本化 PLASMA configuration HIL PASS authority |

Manufacturer-specific evidence 名稱、DFP terminology、CFG naming 或 vendor tool 狀態只能由 adapter 映射到上述共同 evidence class；**不得直接成為 Product Level enum 或 visibility rule。**

Promotion edge 與 canonical blocker taxonomy：

| Promotion edge | Blocker code | 意義 |
|---|---|---|
| L0 → L1 | `NO_PROGRAMMING_ROUTE_EVIDENCE` | Exact ICPN 已成立，但尚無 canonical source-backed programming route |
| L1 → L2 | `MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED` | 已有 canonical mapped target route，但尚未完成版本化 Programming Provider qualification |
| L1 → L2 | `BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED` | 已有 source-backed backend candidate，但仍是 research-only |
| L1 → L2 | `PROVIDER_QUALIFICATION_INCOMPLETE` | Provider review 已存在，但 state 仍為 UNKNOWN/CANDIDATE |
| L1 → L2 | `PROVIDER_QUALIFICATION_BLOCKED` | Provider review 明確為 BLOCKED |
| L1 → L2 | `PROVIDER_DECLARED_UNSUPPORTED` | Provider review 明確為 UNSUPPORTED |
| L2 → L3 | `PLASMA_VERIFIED_CONFIGURATION_MISSING` | 軟體已 PROGRAMMABLE，但尚無版本化 PLASMA configuration HIL PASS |

此 taxonomy 是 **Manufacturer-neutral**。ST、NXP、Microchip 不得新增同義但 Manufacturer-specific 的 blocker code；各 Manufacturer 的 source adapter 只能提供 evidence，不能直接決定 Product Level。若未來新增新的 canonical route 類型或 Level 3 authority，必須先擴充共同 taxonomy／observer，再讓 CI 通過；不得默默歸類。

Framework report 必須至少輸出：

- 全域與逐 Manufacturer 的 L0/L1/L2/L3 Unique Exact ICPN counts；
- Customer IC Selector 可見數（L1–L3）與 Job Picker 可選數（L2–L3）；
- canonical promotion evidence class counts；
- 各 promotion edge 的 blocker counts；
- Catalog revision identity；
- `execution_authorized_by_framework=false`，明示 report/Level 永遠不是 execution grant。

Current implementation: `software/python/plasma_web/catalog_promotion_framework.py`。其角色是 **observer / validator**，不是第二套 promotion engine。

## Catalog Level implementation — IC Detail 與 Exact ICPN 驗收漏斗（已採納規範）

IC Detail 的三個操作區塊仍是 **IC Information / Programming / PLASMA Compatibility**，但 Catalog maturity 使用四級：**Level 0 identity inventory → Level 1 programming candidate → Level 2 programmable → Level 3 PLASMA verified**。Level 0 是 Internal Research only；Level 1 是 Customer-facing Programming Candidate，可進一般 IC Selector 但不可進 Job Picker。

**Implementation status（不得與 Catalog Level 混用）：**Identity infrastructure 已建立；Owner 於 2026-10-15 核准 Programming Qualification 工作；PLASMA Compatibility implementation 仍延後。這是專案工作進度，**不是任何 ICPN 的 Catalog Level**。

| Catalog Level | UI 區塊 | 個別 Exact ICPN 的進入／完成條件 | 不得推論 |
| --- | --- | --- | --- |
| **Catalog Level 0 — Research Inventory** | **01 IC Information** | **`DISCOVERED`**：完整商用 Exact ICPN 已由 Manufacturer 官方來源無歧義確認；可持續補強 Package、Pin Count、Flash、RAM、Working VDD、I/O Supply、Analog Supply、Temperature、Core 等欄位。`INFORMATION_COMPLETE` 是獨立欄位品質里程碑，不改變 Catalog Level。 | 只進 Internal Research Registry；**一般 User 不可見**。 |
| **Catalog Level 1 — Programming Candidate** | **02 Programming Research** | **`PROGRAMMING_CANDIDATE`**：Level 0 Exact ICPN 已具至少一條 source-backed Provider／target／driver／algorithm／ROM-IAP／官方 programming route，applicability 可合理映射到該 ICPN／Base／Family，值得做完整 qualification。 | 可進一般 IC Selector，作為 qualification／客戶委託候選；**不可進 Job Picker、不可宣稱可燒錄**。 |
| **Catalog Level 2 — Programming Qualified** | **02 Programming** | **Catalog Level 1 的子集合**：對精確 ICPN 依原廠 programming evidence 與版本鎖定 Programming Provider 驗證 Silicon ID／Revision、Target／Device mapping、Flash Driver、Bank／Geometry／Security 與宣告的 Erase／Program／Read／Verify 操作。至少一個 `ProgrammingQualification.state == SUPPORTED` 才導出 `PROGRAMMABLE`。 | 家族名稱、共用 Core、單獨 CFG／Driver 字串或 Candidate evidence，都不足以取得 Level 2。 |
| **Catalog Level 3 — PLASMA Verified** | **03 PLASMA Compatibility** | **Catalog Level 2 的子集合**：至少有一組明確版本化的 **IC／Package＋PPU／Site＋Socket／Adapter＋FPGA／PS／Provider** configuration，通過供電、Pin Mapping、SWD／JTAG、保護與實機 HIL，才導出 `PLASMA_VERIFIED`。 | Level 3 只證明至少一組 configuration；不代表所有 Site／Adapter／版本都通過，也不能免除當次 Job／Batch 的安全檢查。 |

### 四級數量契約：統一以 Unique Exact ICPN 計算

在**同一廠商、同一研究庫 Snapshot 與相同 OpenOCD 軟體資格範圍**下：

- **Catalog Level 0 `DISCOVERED`**：完整商用 Exact ICPN 已由原廠證實身分，保留於 Research Registry。
- **`INFORMATION_COMPLETE`**：Level 0+ 中必要 IC Information 欄位均通過證據驗收者；**獨立統計，不是 Catalog Level**。
- **Catalog Level 1 `PROGRAMMING_CANDIDATE`**：Level 0 中已有 source-backed programming route、值得進一步 qualification 者。
- **Catalog Level 2 `PROGRAMMABLE`**：Level 1 中，至少一個指定 Programming Provider／版本／操作 qualification 為 `SUPPORTED` 者。
- **Catalog Level 3 `PLASMA_VERIFIED`**：Catalog Level 2 `PROGRAMMABLE` 中至少有**一組指定 PLASMA 硬體／軟體配置** HIL `PASSED` 的精確料號。

**強制不變量：Catalog Level 3 `PLASMA_VERIFIED` ⊆ Catalog Level 2 `PROGRAMMABLE` ⊆ Catalog Level 1 `PROGRAMMING_CANDIDATE` ⊆ Catalog Level 0 `DISCOVERED`。** 四個 Catalog Level 都以 Distinct Exact ICPN 計數；不能把 CFG 數、家族數、Programming Profile 數、Research 候選數或 HIL 測試次數混入分母。**通過 HIL 的配置組合數另計。**

Catalog Level 2 若不符合、證據不足、在指定 Provider／版本不支援，或日後軟體資格失效，**撤銷 Level 2 `PROGRAMMABLE`，必要時同步撤銷依賴它的 Level 3 `PLASMA_VERIFIED`；若 source-backed programming route 仍成立則退回 Level 1，若 route 也失效則退回 Level 0，但 Exact ICPN identity 仍保留**，並記錄不符合原因、Provider 版本及原廠證據。Catalog Level 3 失敗只撤銷該硬體配置的 PASS；唯有**原廠身分本身不成立**，才依獨立 Catalog Level 1 身分修正流程處理。

### Catalog Level 0 / 1 — Exact ICPN identity 與 programming relevance

**OpenOCD CFG-first Reverse Discovery 是預設的「研究入口／選料策略」，不是 IC Information 的原廠規格證據。** 任何替代 Provider／版本應依既有政策獨立核准。

1. **由 Config 反推候選 Family／Base Device**：使用指定 OpenOCD 版本／Commit 的 `tcl/target/*.cfg`，遞迴展開 Tcl Include，解析 Target、Flash Bank 與實際 Flash Driver。記錄 Provider、版本、CFG、Driver、來源雜湊，以及映射是否明確／通用／部分成立。單看 CFG 檔名或 Family 前綴不能證明精確 IC 可燒錄。
2. **反查原廠完整料號**：由已辨識家族尋找原廠 Product、Package／Quality、Ordering Table、Datasheet 或官方 Parametric Export。把**該家族中原廠實際列出的各種封裝與商用後綴料號**逐一建檔。**Catalog Level 0 不要求每一個封裝後綴都有獨立 OpenOCD CFG、Driver 或 Silicon ID 證據**；但不能拼湊不存在的料號、把 Product 標題的 Active 當成每個 Material 都 Active，或把只有 Family／DFP Alias 的紀錄冒充完整 ICPN。
3. **`IDENTIFIED` 最低門檻**：`manufacturer`、**完整商用 `icpn`**、由原廠確認的 Base／Family 對應、官方 Source URI、來源證據作用範圍（Material／Ordering 與 Family／Product 必須分清）、觀察時間與身分證據狀態。同一完整商用身分去重；Lifecycle 與材料後綴分開記錄。猜測、模糊命中、衝突或不完整料號保持 `RESEARCH_ONLY`／`IDENTITY_DISPUTED`，**不得標為 Catalog Level 0 `DISCOVERED`**。
4. **原始證據封存與 Catalog Level 0 數量分開管理**：能取得時封存原廠 XLSX／PDF／HTML／API 原始 Bytes 與 SHA-256。若無法封存，必須標記 `SOURCE_BYTES_NOT_ARCHIVED`，保留官方 URL、觀察時間、Source Scope，**不可聲稱已保存原廠 Binary SHA 或完整的原始檔位元重播**。但是可由官方**個別物料紀錄直接確認且無歧義**的 ICPN，仍可計為 `IDENTIFIED`；未封存來源須另列缺口。Catalog Level 0 `DISCOVERED` 決定 Canonical Device Registry membership，但**不構成 Catalog Level 2、IC Selector visibility 或執行授權**。
5. **欄位持續補強，不阻擋 `IDENTIFIED`**：補齊 `base_device / package / pin_count / flash / ram / working_vdd / io_supply / vdda_or_analog_supply / temperature`，以及適用的 Core／Architecture。保留原始單位、工作模式、文件版次／表格、Exact／Family 適用範圍與 `VERIFIED／PARTIAL／UNKNOWN／CONFLICT`。如原廠明確證明沒有某個獨立電源軌，可使用附證據的 `NOT_APPLICABLE`；不得以 Absolute Maximum Ratings 當 Working VDD，亦不可將 VREF 混為 VDDA。
6. **`INFORMATION_COMPLETE` 門檻**：所有適用的必要欄位均有精確料號或明確涵蓋該料號的 Family 官方證據，結果為 `VERIFIED` 或有來源的 `NOT_APPLICABLE`。必要欄位存在 `UNKNOWN／PARTIAL／CONFLICT` 時不得列為資訊完整，**但不撤銷 Catalog Level 0 `DISCOVERED`**。來源原檔封存覆蓋率再單獨呈現。
7. **Catalog Level 邊界**：Catalog Level 0 不宣稱 Erase／Program／Verify 可用、不授權 `SUPPORTED`、不建立已驗證 Programming Profile，也不授權 Job／Batch 或實機 HIL。通過 Catalog Level 0 `DISCOVERED` 的 Exact ICPN 僅可由 Internal Research Registry／Engineering inventory 查詢；具體 programming route 成立後升到 Level 1 `PROGRAMMING_CANDIDATE`，此時才可進一般 Customer-facing IC Selector；達到 Level 2 `PROGRAMMABLE` 後才可進 Job Picker。尚未達 `IDENTIFIED` 的 Research-only 候選不得混入任何 canonical product surface。

**案例：** 從 `lpc8xx.cfg` 發現家族後，可反查 NXP 官方 LPC811／812／822／824 各自存在的完整商用後綴。每一筆**經原廠個別確認**者即可進入 Catalog Level 0 `DISCOVERED`；即使某個 Silicon Revision 尚無 `lpc2000.c` 支援證據，也是在 Catalog Level 2 再檢查。**一個 CFG 不等於一個 ICPN，也不代表整個家族已 `SUPPORTED`。**

**Catalog Level 0 identity 驗收輸出：** Catalog Level 0 `DISCOVERED` Exact ICPN 清單、官方來源與取得時間、Family／Ordering Variant Crosswalk、OpenOCD 研究入口、逐欄位覆蓋率、身分衝突、原始證據封存缺口、可重播的來源檢查，以及獨立的 `INFORMATION_COMPLETE` 數量。**不得藉此修改 Catalog Level 2／3 結果或 Job／Batch 執行權限。**

### Catalog Level 1 — Cross-vendor canonical discovery method

現階段的 ST、NXP、Microchip 及未來任何 Manufacturer 必須使用**同一套 discovery 判定流程與 canonical output**。差異只允許存在於原廠資料取得 adapter，不允許存在於 Catalog Level 定義、欄位狀態、證據門檻或 Selector／execution 語意。

固定流程：

1. **Capability Seed**：從鎖定 Programming Provider（目前為 OpenOCD）的 Target／Include／Flash Driver／Silicon Probe Rule 建立技術研究入口；只記錄實際 evidence 與缺口，不建立另一套數字型研究狀態。
2. **Official Manufacturer Identity Acquisition**：回到原廠官方 Material／Ordering／Product／Parametric／DFP／Datasheet 等來源取得 Exact ICPN；不得用 CFG、家族名稱或後綴規則創造商用料號。
3. **Exact ICPN Crosswalk**：明確保存 `manufacturer + exact_icpn + base_device/family + source_scope`。只有無歧義官方完整商用料號可標為 Catalog Level 0 `DISCOVERED`。
4. **IC Information Projection**：Package、Pin Count、Flash、RAM、Working VDD、I/O Supply、VDDA、Temperature 等欄位各自使用 `VERIFIED／PARTIAL／UNKNOWN／CONFLICT／NOT_APPLICABLE`；未知不得補零、不得跨 rail 複製、Family evidence 不得假裝 Exact evidence。
5. **Programming Handoff**：Catalog Level 0 `DISCOVERED` 只有在存在 source-backed programming route 時才升到 Level 1 `PROGRAMMING_CANDIDATE`；Level 1 經版本鎖定 Programming Provider + 原廠 programming evidence 完成 Exact ICPN qualification 且為 `SUPPORTED` 才升到 Level 2 `PROGRAMMABLE`。
6. **Registry / Selector / Job / Execution Separation**：L0 `DISCOVERED` 決定 Internal Research Registry membership；L1 `PROGRAMMING_CANDIDATE` 起即可進一般 Customer IC Selector；L2 `PROGRAMMABLE` 起才可進 Job Picker；L3 提供 verified configuration 狀態。Catalog visibility、Job selection 與最終 execution entitlement 是三個不同 gate。

**本 ADR-0002 是此跨廠牌 discovery 方法的唯一規範來源。** 新的 ST／NXP／Microchip 或其他 Manufacturer discovery 工作、review 與 consumer 都必須直接遵守本節的 Catalog Level／field naming、證據門檻與 selector/execution 邊界；既有 vendor-specific historical artifacts 可以保留作證據與重播，但不得自行定義另一套 Catalog Level 或 visibility policy。

### Vendor-specific official source adapters

不同原廠的官方介面可以不同，例如 ST Product Selector/eStore、NXP Material/Buy-Parametrics、Microchip MCP/DFP/Parametric Chart。這些都只是 **source adapter**；輸出必須遵守上述共同 contract。

### Catalog Level 1 — official manufacturer bulk information acquisition — Microchip source-adapter example

**Decision / implementation method:** Use the manufacturer's **Parametric Search chart export → official MCP exact-ordering crosswalk → targeted datasheet evidence** as the default Microchip Catalog Level 1 acquisition pipeline. This is an **approved workflow contract**, not a statement that a chart exporter, unattended scraper, or all-Microchip complete ingestion already exists. Other manufacturers may use equivalent official, source-bound bulk exports under the same field-level contract.

| Evidence layer | Acquisition and role | Evidence limitation |
| --- | --- | --- |
| **A. Parametric Search / XLSX (bulk)** | Navigate the official Microchip product category/MCU subcategory chart; use **Download Chart → All Data** to export the chart's products **and columns** as XLSX; retain the original file and chart URL/category. Manufacturer guide: [DS00004852A](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/MarketCommunication/Promotions/Parametric-Search-User-Guide-00004852.pdf), “Download Chart Button”; [current online guide](https://www.microchip.com/en-us/products/selection-tools/parametric-search-landing-page/user-guide). | **All Data is chart-scoped**, not all Microchip exact commercial ordering codes or all lifecycle states. A chart row can represent a base device rather than an orderable SKU; available columns vary by chart. A successful file export is a source capture, not automatic per-ICPN verification. |
| **B. Microchip official MCP (exact-ordering evidence)** | Query the [official Microchip MCP product server](https://www.microchip.com/en-us/resources/model-context-protocol-server) via documented Streamable HTTP endpoint `https://api.microchip.com/mcp/resources`, using bounded `search_products` queries and checked pagination; archive original requests/responses. Extract exact `partNumber`, source-provided `basePartNumber`, package/lead count and other actually returned fields. | Search is **not a proven complete enumeration API**. Related/fuzzy hits, vendor base aliases, missing/ambiguous results, or `NOT_FOUND` do not establish full SKU coverage, EOL, or silicon compatibility; fields absent from a response remain unknown. |
| **C. Manufacturer datasheet / ordering table (targeted gaps)** | For absent or conflicting fields, obtain the official versioned family/device document and bind **revision + exact ordering table / electrical table + page or section + applicability** to each finding. In particular distinguish working VDD, `VDDIO`, `VDDA`/`VDDANA` and internal rails such as `VDDCORE`. | Family electrical specs require exact-variant applicability checks; a family table alone stays `PARTIAL`. Only a source explicitly applying a field to an exact ICPN can justify `VERIFIED` for that field. Do not retrieve Programming Guide/Flash-controller semantics in Catalog Level 1. |

**Execution sequence (source-first, repeatable, fail closed):**

1. **Select bounded cohort and chart:** prioritize families for which a pinned Programming Provider route or strong manufacturer demand already gives a concrete research reason, starting from the two existing ATSAMD21G18A pilot order codes. Record manufacturer, chart URL/ID, category/subcategory, selection/view settings, export scope, acquisition time and any manufacturer-published source revision/date **separately**. A manual XLSX export is acceptable as an initial capture; no undocumented export API or bypass of HTTP 403 is assumed or authorized.
2. **Archive original bytes before parsing:** store the unmodified XLSX/PDF/MCP response bytes and SHA-256 (and capture manifest containing URL, timestamp, media type, file size, chart/document identifier, acquisition outcome and licensing/access limitations). Verify hashes in an independent offline replay. Temporary CI artifacts with expiration are **not** permanent source archives; unavailable sources record explicit blockers rather than invented hashes.
3. **Normalize chart fields without fabricating evidence:** preserve the exact raw column name, raw value, original units, chart scope and provenance per field. Map only observed data into `manufacturer/icpn/base_device/package/pin_count/flash/ram/vdd/io_supply/vdda/temperature` and optional `core_architecture/core_model`; keep unmatched columns and nulls. Never silently coerce `UNKNOWN` to 0, treat KB as KiB, or apply a base-device number to every commercial suffix.
4. **Crosswalk commercial ICPNs:** use separately archived, bounded MCP query/pagination results and official exact ordering-code tables to build **`exact ICPN ↔ manufacturer-reported base device ↔ chart family row`** links. Deduplicate on complete original commercial order code; quarantine fuzzy matches and conflicting identities. Only exact-source rows may substantiate exact package, pin and temperature fields. A chart-only family value may be useful `PARTIAL` evidence but cannot be auto-upgraded to exact `VERIFIED`.
5. **Resolve missing supply fields selectively:** inspect the official datasheet's *power-supply and operating conditions* material only when the chart/MCP omits or contradicts a Catalog Level 1 information field. Retain distinct rail names, mode/temperature/voltage conditions and any restrictions on multiple supplies; leave unjustified `io_supply` or `vdda` as `UNKNOWN` or `PARTIAL`, not copies of `vdd`.
6. **Reconcile independently:** attach a source locator, original record/cell or document table, version and original-byte reference to **each** field. Track `VERIFIED / PARTIAL / UNKNOWN / CONFLICT` separately; preserve conflicting observations without winner-by-precedence. No automatic Research→internal `ADMITTED`, Production, software `SUPPORTED`, public selector or physical readiness promotion.
7. **Emit auditable Catalog Level 1 deliverables:** create source manifest/immutable raw-source references, a normalized exact-ICPN research ledger, exact-vs-family evidence crosswalk, per-field coverage and conflict report, and deterministic offline replay/negative tests. Report denominators **per chart/category, observed base devices, observed exact ordering codes, independently admitted identities**, and missing/unresolved rows separately; never interpret a chart or MCP search count as Microchip-wide SKU coverage.

**Acceptance / stop gates:** Test an original-byte replay; reject SHA/version mismatch, duplicate/ambiguous exact order codes, family→exact `VERIFIED` promotion, missing units/source locator, false completeness claims and any Production/Catalog Level 2/3 write. If chart export, MCP capture or datasheet access fails, preserve `SOURCE_NOT_AVAILABLE`/coverage gaps and stop that lane or retry only by a permitted official mechanism. Completion is a **reviewable Catalog Level 1 information cohort with quantified coverage**, not a programming qualification; subsequent cohorts and any identity admission remain separately reviewed. The existing Microchip Research inventory (24,051 source-linked candidates) is **not** automatically bulk-enriched or admitted by this decision.

### Catalog Level 2 — Programming implementation contract（依原廠程式文件做軟體資格篩選）

Catalog Level 2 從 **Catalog Level 0 `DISCOVERED` 的 Exact ICPN 集合**選取候選。逐一核對原廠 Programming Guide／Reference Manual／Datasheet 與指定 Programming Provider／版本，確認實際 Silicon ID／Revision、Target/Driver/Flash Bank、ROM IAP 或 Flash Controller、Geometry、Security、Reset/Clock 條件，及宣告的 **Erase／Program／Read／Verify** 操作，建立有版本與適用範圍的可重用 Programming Profile。

- **`SUPPORTED`**：精確 ICPN 的軟體燒錄適用性與宣告操作有足夠、可重播的版本鎖定證據；不宣稱 PPU／Socket HIL。
- **`CANDIDATE／UNKNOWN／BLOCKED`**：只有部分 Programming Provider 線索，或必要文件／證據不足、相互衝突；Catalog Level 0 `DISCOVERED` 身分仍保留，但 Catalog Level 2 不得標為 `SUPPORTED`。
- **`UNSUPPORTED`（限定版本與操作範圍）**：經審核確定該 Provider／版本／操作不適用；保留 Catalog Level 0 `DISCOVERED` 身分，不可推論全世界任何後端都永遠無法燒錄。
- **退版或資格回歸**：保留原廠料號與歷史證據，撤銷受影響的 Catalog Level 2 `SUPPORTED`，並重新評估依賴它的 Catalog Level 3 `PLASMA_VERIFIED`。

Catalog Level 2 建立獨立的軟體資格權威。Level 1 ICPN 可在一般 IC Selector 中檢視其 qualification gap，但 `job_selectable=false`；只有 `SUPPORTED` 才導出 Level 2 `PROGRAMMABLE` 並取得 Job Picker eligibility。Job／Batch 仍不得把 Selector visibility 或 Job Picker membership 解讀為最終執行授權。

### Catalog Level 3 — PLASMA Compatibility handoff（與軟體資格分離的實機相容性）

Catalog Level 3 僅能對 Catalog Level 2 `SUPPORTED` 的 Exact ICPN 建立**特定配置實機驗證**。驗收證據需鎖定 Device／Package、Socket／Adapter 型號及 Revision、PPU／Site、Pin Mapping、電壓／電流／保護、Debug Interface、PS／PL／Programming Provider 版本及實際 HIL 操作。

Catalog Level 3 `PLASMA_VERIFIED` 統計**唯一 Exact ICPN 數**；通過的實體配置或測試次數另外統計。Catalog Level 2 `PROGRAMMABLE` 而 Socket／PPU 尚未 HIL PASS 的 IC 仍留在 IC Selector，但不得標示 Catalog Level 3 `PLASMA_VERIFIED`。Job／Batch 對選定 Site 的執行期、安全及供電條件維持 Fail Closed；不得用 Catalog Level 1／2 文件捏造 HIL PASS。

### Visibility and execution boundary

The general IC Selector is a **customer capability surface**, not an execution entitlement surface. It exposes Catalog Level 1／2／3 with a Level Filter. L1 means a concrete programming route exists and may represent a customer qualification request; L2 means software programming qualification is `SUPPORTED`; L3 means at least one PLASMA configuration is verified. L0 remains internal-only. Job Pickers request L2/L3 only. No `OpenOCD CFG exists` badge, Catalog Level, Selector visibility or Job Picker membership may be interpreted as final Job／Batch authorization.

## Catalog Level scope of the existing OpenOCD-first and Core/Driver requirements

OpenOCD-first CFG／Target／Driver 分析是**Catalog Level 1 的預設研究入口**，同時為**Catalog Level 2 的燒錄資格**提供技術證據。Catalog Level 1 的身分權威來源仍是原廠完整商用料號；Catalog Level 2 才判定精確 Silicon／Programming Operation 相容性；Catalog Level 3 才判定指定硬體配置的實機 HIL。現行流程不再維護另一套研究優先級 enum。

目前專案 implementation status 為：Identity infrastructure 已建立、Programming Qualification 已核准執行、PLASMA Compatibility implementation 延後。專案進度**不得被解讀為任何 ICPN 的 Catalog Level**。舊研究資料、來源 Hash 與未完成的欄位／資格缺口均保留，不得因本次修訂而回溯視為 `IDENTIFIED`、`INFORMATION_COMPLETE` 或 `SUPPORTED`。



## Cross-vendor discovery execution order

現階段的 ST、NXP、Microchip 與未來任何 Manufacturer 一律使用相同的 discovery 執行順序；差異只允許存在於原廠資料取得介面。

1. **鎖定 Programming Provider 與版本**：使用 `release/openocd.json` 或另行核准的 Provider Registry，保存 Provider、Version／Source Commit、Target CFG、Include Graph、Flash Driver、Silicon Identity／Probe Rule 與內容雜湊。
2. **由軟體能力反查原廠裝置範圍**：Capability Seed 只能建立技術研究入口，不能建立商用料號、Catalog Level 1 身分或 Catalog Level 2 支援結論。
3. **只由原廠官方來源取得 Exact ICPN**：使用各 Manufacturer 官方 Material／Ordering／Product／Parametric／DFP／Datasheet 等來源，保存 Source URI、Scope、Observation Time 與可取得的原始 Bytes／Hash。不得依 CFG 名稱、Family 前綴或 suffix grammar 創造不存在的料號。
4. **Catalog Level 1 判定**：只有原廠完整商用 Exact ICPN 身分無歧義者可標為 `IDENTIFIED`。IC Information 各欄獨立使用 `VERIFIED／PARTIAL／UNKNOWN／CONFLICT／NOT_APPLICABLE`，不得用預設值填補未知。
5. **Catalog Level 2 判定**：只有 Catalog Level 0 `DISCOVERED` 的 Exact ICPN 可進 Programming review；必須完成版本鎖定 Provider、原廠 programming evidence、Silicon／Revision、Flash geometry／security 與宣告操作的適用性驗證，才可標為 `SUPPORTED`。
6. **Catalog Level 3 判定**：只有 Catalog Level 2 `SUPPORTED` 的 Exact ICPN 可建立指定 PPU／Site／Socket／Adapter 配置的實機驗證；通過者標為 `PASSED`。
7. **停止與重啟規則**：證據不足就保留當前 Catalog Level／qualification 的真實狀態與 missing-evidence 清單並停止擴張；只有 Provider 版本、原廠證據或核准產品需求發生實質變化時才重新開案。缺證據不能推論成永久不支援。
8. **跨 Manufacturer 一致性**：相同證據強度必須得到相同 Catalog Level 判定；不得因 ST、NXP、Microchip 或任何 Manufacturer 使用不同網站／API 就放寬 identity、field、programming 或 HIL 證據門檻。

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
- 對具有 source-backed Target／Driver 路徑的族群，仍須個別確認 Flash driver 操作、晶片識別／revision、bank/base/geometry、所需 transport、目標限制以及 Exact ICPN 映射；若任一關鍵證據不足，Catalog Level 2 維持 `CANDIDATE`／`UNKNOWN`，不宣稱 `SUPPORTED`。
- JTAG 不限 ARM；Microchip PIC32MX/MIPS 與部分 AVR JTAG 是非 ARM 路線的優先檢查範例。SWD 對 Cortex-M 特別常見，但不得假設所有 ARM MCU 都可由 PLASMA 所選 OpenOCD Flash Driver 燒錄。
- 不建立額外的研究優先級 enum。Catalog Level 2 只使用 `UNKNOWN／CANDIDATE／SUPPORTED／UNSUPPORTED`；研究排程可依業務需求與 evidence gap 決定，但不得寫入另一套產品狀態。

### 3. Core-aware Coverage Metrics

報表最少以 `manufacturer × core_architecture/core_model × debug_transport × provider_version × flash_driver` 分組，並**明確分開不同母體與顆粒度**：

1. 原廠 Research 候選身分數（DFP 名稱或精確 ICPN 需分開；未完成商業身分校驗者不可混入精確 ICPN 總數）。
2. OpenOCD Target／Driver source-backed **Device/Profile** 數量（不是精確 ICPN 數）。
3. 已完成 OpenOCD 軟體 `SUPPORTED` 的 **精確 ICPN** 數量與預設 PLASMA Catalog 可見數。
4. 已完成特定 Socket／PPU／Site Configuration HIL 的數量（不是軟體支援 ICPN 數）。
5. Catalog Level 2 的 `CANDIDATE`、`UNKNOWN`、`UNSUPPORTED` 分別統計；Research backlog／archive 另計工作量，不能把 backlog 類別變成 Catalog Level 狀態，也不能以 0 代替未知。

若要驗證「OpenOCD 支援的 IC 以 ARM 為多數」，必須先固定 **Provider／版本、Microchip 或跨廠範圍、統計單位（Target、Device/Profile、精確 ICPN）和母體**，再計算各 Core 比例；不允許以 Target Config 檔案數、Research 24,051 候選數或對 Cortex-M 生態的直覺直接宣稱多數。未知／未分類的比例必須揭露。

**Migration boundary:** 此節為已批准的架構實作要求，**不是目前 Catalog API、IC Support Schema 或 Microchip ICPN 資格審核已完成的聲明**。不得藉此更新 Production ICPN 或變更 Job/Batch 安全驗證；實作仍需單獨 PR／CI／Owner Merge Gate。

## Status dimensions

建議的邏輯維度如下（**為政策模型，並非宣稱現行 API 已有同名欄位**）：

| Programming Qualification state | Catalog Level derivation | Product surface |
|---|---|---|
| `UNKNOWN` | 保持 Level 1 | Device Registry only |
| `CANDIDATE` | 部分 Target／Driver／Silicon 線索，尚未達可證明燒錄條件 | **顯示**，明示 Candidate |
| `SUPPORTED` | 版本鎖定、Exact ICPN 對應、Flash 操作範圍及來源證據達成軟體支援審查 | **顯示**，明示 Supported |
| `UNSUPPORTED` | 已審查所指定 Provider／版本／操作不支援 | **顯示**，明示 Unsupported |

硬體可以另行記錄 `NOT_TESTED`、`READY`、`PASSED`、`FAILED`，但實際上 **Socket / Adapter / PPU / Site 應是不同的、有版本與 Configuration identity 的證據**，不應用單一扁平狀態掩蓋設備和治具差異。

範例：`openocd_software_support=SUPPORTED` 且 `socket_validation=NOT_TESTED`，IC 可以被搜尋與選取；是否能對某座 Site 執行燒錄，由執行階段另行判定，不應自動允許寫入。

## Migration gap and ownership

- **Accepted now:** 跨 Manufacturer Catalog Level 0／1／2／3 定義、**L0 Internal Research Registry、L1–L3 Customer IC Selector、L2/L3 Job Picker** 邊界，以及 Catalog visibility、Job selection 與 execution entitlement 的獨立 fail-closed 邊界。
- **Public API boundary:** `GET /api/devices/search` 是 Customer IC Selector projection，只允許 `levels` 為 1／2／3 的子集合；Level 0 request 必須 fail-closed。Internal Research Registry 不透過此 public endpoint 暴露。Pagination、`total_count` 與 `catalog_size` 必須在 server-side Level projection 後計算。
- **Migration rule — no active Phase fields:** active API／runtime／canonical output 不得出現 `phase1_*`／`phase2_*`／`phase3_*` 欄位；不提供 alias。只有 immutable/source-locked historical evidence 可原樣保留舊欄位作 input，且不得直接投影到 Product payload。
- **Not yet fully normalized:** ST／NXP／Microchip 的歷史資料仍分散於不同 artifact／resolver；後續 migration 要把它們投影成相同 Catalog Level／qualification 欄位與 UI payload，而不是再建立 Manufacturer-specific policy。
- 現行 `docs/architecture/icpn-catalog-admission-policy.json` 的 `requires_deterministic_backend_route_or_explicit_mapping_state`，是內部 **identity admission** 契約，**不得被誤讀為 Public Catalog 可見規則**。
- 現行 `backend.mapping_status=mapped` 主要表示確定性路由，尚不能概括為已做所有 software qualification；`no_mapping` 更不能當 Supported。Research `backend_candidate` 不可轉為可執行路由。
- 保留既有 Production exact ICPN 資料與研究證據，不透過本 ADR 刪除或大規模匯入 Production rows。
- 後續實作由 [Issue #849](https://github.com/physicslu/plasma/issues/849) 追蹤，須分開審查 source/version qualification、Product API／UI 及 execution gate regression。ST、NXP、Microchip 使用**同一套政策**；不得對不同廠商放寬。

## Validation / acceptance

**後續實作 PR 必須新增的 Catalog Level Funnel 契約測試：**

- 一份 OpenOCD CFG 可反查原廠家族內多個官方完整商用封裝／Ordering Variant；每筆原廠個別證實者可獨立成為 Catalog Level 0 `DISCOVERED`，不需每筆各有 CFG；**臆造後綴、只有 Product Title 的 Active** 都不得計入。
- 分別報告 Catalog Level 0 `DISCOVERED`、Level 1 `PROGRAMMING_CANDIDATE`、Level 2 `PROGRAMMABLE`、Level 3 `PLASMA_VERIFIED`；`INFORMATION_COMPLETE`、原檔封存率與逐欄位證據狀態另行統計，不能當作 Catalog Level。
- Programming Qualification 證據不足或指定 Provider／版本不支援時，Exact ICPN 仍保留 Level 0 `DISCOVERED`；若 source-backed programming route 仍成立可留在 Level 1。只有 qualification `SUPPORTED` 才升到 Level 2；只有指定 configuration HIL `PASSED` 才升到 Level 3。
- 四級均以 **Distinct Exact ICPN** 統計，不得混入 CFG 檔數、Base Device、Family 頁數、Profile 數或 HIL 測試執行次數；每個 Snapshot 驗證 `L3 ⊆ L2 ⊆ L1 ⊆ L0`。資訊完整數和實體配置組合數獨立報告。
- Catalog Level 3 `PLASMA_VERIFIED` 必須有指定配置；Level 2 `PROGRAMMABLE` 但 Socket／PPU 未測的 IC 仍可顯示於 Selector，但不得標成 Level 3；單一硬體失敗不得直接撤銷 Level 2。

1. 使用實際 Level 0 `DISCOVERED` rows 計算 **Internal Research Registry**；一般 IC Selector 的 `catalog_size`／`total_count` 必須由所選 L1／L2／L3 Filter 的 server-side projection 計算；Job Picker 只以 L2／L3 計算，不手填或繼承歷史 coverage 數。
2. 測試 L0 Exact ICPN **不會由 public IC Selector API 回傳，且 `levels=0` fail-closed**；L1 Exact ICPN 可由一般 Selector 搜尋，但 `job_selectable=false`；任何 CFG／family/source candidate 都不得自行導出 `PROGRAMMABLE`。
3. 測試 `ProgrammingQualification.state == SUPPORTED` 的 ICPN 導出 Catalog Level 2 `PROGRAMMABLE` 並出現在 IC Selector；即使 Socket／PPU 未測試也維持 Level 2，但不得標為 Catalog Level 3 `PLASMA_VERIFIED`。
4. Internal Research Registry 與 Customer IC Selector 必須使用同一 Canonical Identity source，但採不同 projection：Internal Registry = L0+；Customer Selector = L1–L3；Job Picker = L2/L3。Catalog Level 3 增加 verified configuration 狀態。
5. 保持 Job／Batch 的 runtime executable、選定 Site、電氣限制、配置安全與硬體審核獨立 fail-closed；嚴禁由 Catalog presence 推導可執行。
6. Research-only Microchip 24,051 候選與原廠資料庫不受顯示規則刪除或修改。
7. Core／Transport／Target／Flash Driver／Exact ICPN 每一層具可審核來源與版本，且測試同 Core 但不同 Flash Driver 不得被誤判可互換；多核心或未知 Core 不可被強制歸類為 ARM。
8. 測試 Cortex-M/SWD/CFG-only 仍只能形成 Catalog Level 2 `CANDIDATE` 或 `UNKNOWN`，以及 MIPS/PIC32MX 或 AVR/JTAG 等**非 ARM**來源線索可依完全相同的證據門檻進行審核；source-backed 路徑不得自動晉升 `SUPPORTED`。
9. Core 統計顯式標明 Programming Provider 版本與 Target／Device/Profile／Exact ICPN 各自分母，並分別報告 Catalog Level 1／2／3 狀態；不得以 Research 候選總數作為已支援分母，也不得未經統計就宣稱 ARM 占多數。

## Alternatives considered

- **所有 Research 候選都直接顯示**：拒絕；尚未通過 Catalog Level 0 `DISCOVERED` 的字串可能是 alias、family name、模糊命中或不存在的商用料號。
- **一般 IC Selector 顯示 L1–L3，並提供 Level Filter；L0 保持 Internal-only；Job Picker 顯示 L2/L3**：**採用**。這讓客戶可看見可委託 qualification／validation 的候選，同時不把純 identity inventory 當成產品能力。
- **只顯示 Catalog Level 3 `PLASMA_VERIFIED`**：拒絕；把治具／硬體可取得性錯當成 IC identity 或軟體資格門檻。
- **Catalog Level 0 `DISCOVERED` 全部直接進一般 IC Selector**：拒絕；大量尚無任何 `SUPPORTED` Programming Qualification 的 IC 會形成不可操作的 Product noise。

## Decision summary

```text
Manufacturer Research / Discovery
       ↓ exact Manufacturer ICPN confirmed
Catalog Level 0 — DISCOVERED
Research Registry
       ↓ source-backed programming route exists
Catalog Level 1 — PROGRAMMING_CANDIDATE
Customer IC Selector / Qualification Candidate
       ↓ ProgrammingQualification.state == SUPPORTED
Catalog Level 2 — PROGRAMMABLE
Customer IC Selector + Job Picker
       ↓ specific PLASMA configuration HIL PASSED
Catalog Level 3 — PLASMA_VERIFIED
       ↓ separate runtime execution entitlement
Job / Batch still requires applicable qualification + installed Runtime
    + route + electrical/safety + selected-site requirements
    → fail closed
```

**Normative clarification (2026-10-16):** Exact ICPN identity alone is Level 0 and remains Internal Research only. Source-backed programming relevance is Level 1 and is the minimum Customer IC Selector visibility level. Job Picker eligibility begins at Level 2 `PROGRAMMABLE`. Level 3 is configuration-specific HIL evidence and never replaces execution-time safety gates.
