# ADR-0002: PLASMA Catalog 以 OpenOCD 軟體燒錄支援為顯示門檻，硬體驗證獨立管理

- **Status:** Accepted (product policy; implementation phases defined, Phase 1 active; public Catalog migration outstanding)
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

## Implementation Phases — three IC detail sections (owner-directed)

The three panels on the right of the IC detail screen represent **three independent evidence products and three implementation phases**. They must not share a single vague `supported` / `ready` outcome. **Currently only Phase 1 is authorized for new work.** The phase order is a scope and acceptance boundary; it does not override the two existing engineering approval gates.

| Phase | IC detail section | Evidence scope | Acceptance / non-claim |
| --- | --- | --- | --- |
| **Phase 1 — CURRENT** | **01 IC Information** | Exact manufacturer commercial ICPN, Base Device, Package, Pin Count, Flash, RAM, working VDD, I/O Supply, VDDA, temperature; optional sourced Core/Architecture. Each field has manufacturer provenance, units, source version/time/hash where available and explicit missing/partial/conflict status. | Reproducible manufacturer identity and information evidence; per-field coverage/gaps. **No Flash-programming software qualification, no reusable Programming Profile, no HIL or execution claim.** |
| **Phase 2 — DEFERRED** | **02 Programming** | Manufacturer Programming Guide / Reference Manual / User Manual, silicon ID/revision, Flash Controller/ROM IAP, geometry/banks/security, version-locked OpenOCD Target/Flash Driver/Transport, erase/program/read/verify operation applicability, reusable manufacturer-derived Programming Profile and exact ICPN mapping. | Only an independently qualified exact ICPN may be `openocd_software_support=SUPPORTED`. Implement the uniform default public IC Selector/Catalog visibility and counts under Issue #849. |
| **Phase 3 — DEFERRED** | **03 PLASMA Compatibility** | Independent PPU / Site / Socket / Adapter configuration identity and revision, electrical/voltage/pin mapping, fixture endurance, physical HIL, compatibility and actual selected-site execution constraints. | Configuration-specific physical qualification and runtime safety. Software `SUPPORTED` alone is not Hardware Ready or Job/Batch permission. |

### Phase 1 — IC Information implementation contract (active)

1. The current task is to build and validate **only the data shown in 01 IC Information**, plus per-field source evidence and information completeness. Verify Exact ICPN identity before internal admission according to its own existing contract. Manufacturer Research records may remain incomplete without being erased or falsely admitted; an exact SKU *candidate* is not the same as a fully validated manufacturer identity.
2. Record `manufacturer`, `icpn`, `base_device`, `package`, `pin_count`, `flash`, `ram`, `vdd`, `io_supply`, `vdda`, `temperature` and applicable sourced `core_architecture/core_model`. For each numeric/specification field retain original units, official document/source identity and available hash, source scope (exact order code vs device family), and `VERIFIED` / `PARTIAL` / `UNKNOWN` / `CONFLICT` evidence state. Do not turn an empty/unknown value into `0`, a default family number, or a claim verified only by model-name parsing.
3. Phase 1 metrics are **manufacturer research identity counts, exact identity-admitted counts, and per-field evidence completeness with explicit unknown and conflict denominators**. Core is an indexing/classification dimension, not a proxy for SWD/Flash support. P0/P1/P2 OpenOCD-first classification may guide how to *prioritize* Phase 1 information work, but a Phase 1 result does not require detailed Flash Driver or programming-guide research.
4. **Phase 1 stopping rule:** Do not initiate new detailed ROM IAP, FCF, silicon-specific Flash erase/program/verify, Programming Profile, OpenOCD execution test, PPU, Socket or HIL work. Existing v9–v12 source/driver research may be retained as already-acquired evidence for later phases; it does not constitute a Phase 1 admission/acceptance condition or authorize software `SUPPORTED`.
5. **Phase 1 acceptance:** A source-bound, reproducible dataset and tests for intended exact ICPN cohort; record-level internal-admission state; field-level known/missing/conflicting counts by manufacturer and family; documented blocks and remaining source acquisition work; **no change to Production admission, public Catalog/API/UI selection, installed OpenOCD runtime, firmware/PL or Job/Batch gates unless independently scoped and approved**.

### Phase 2 — Programming handoff (deferred)

Once Phase 1 information deliverables have been reviewed and a distinct Phase 2 scope is authorized, check manufacturer programming specifications against the PLASMA-pinned OpenOCD Provider, exact silicon IDs/revisions, target/driver/flash-bank applicability and the necessary erase/program/read/verify operations. Only this phase can grant new software `SUPPORTED` decisions and implement the product default Catalog/IC Selector support-only view. `CFG exists`, same MCU Core, and current internal identity admission alone never suffice.

### Phase 3 — PLASMA Compatibility handoff (deferred)

Physical HIL and compatibility evidence are independent of Phase 2 software qualification: socket and adapter, target package, PPU/Site electrical compatibility and configuration revisions are separate records. A software-qualified exact ICPN may be displayed with hardware `NOT_TESTED`, while Job/Batch still fails closed on unsatisfied execution conditions. Phase 1 or 2 must not synthesize a hardware PASS.

### Visibility and status boundary during phased migration

This ADR's already-accepted final **user-facing default selectable Catalog = exact software `SUPPORTED` only** policy remains unchanged, but it is **not implemented merely by adopting these phases**. Phase 1 IC Information may be examined in internal Research/admin detail views; this does not make incomplete or unqualified ICPNs eligible in the default product selector. The current IC Selector/API visibility migration belongs to Phase 2 (Issue #849) and remains explicitly outstanding. No existing `OpenOCD CFG exists` badge may be interpreted as an affirmative programming-qualification result.

## Phase scope of the existing OpenOCD-first and Core/Driver requirements

The original OpenOCD-first prioritization, detailed Target/Flash Driver
qualification, and supported-only public Catalog implementation below describe
**Phase 2 Programming requirements**, not prerequisites to finish Phase 1
IC Information. P0/P1/P2 may still be retained as existing, low-cost
research-priority metadata in Phase 1, but no new Phase 2 or Phase 3
work is permitted under the active Phase 1 scope. Existing source-locked
manufacturer or OpenOCD investigations are preserved, not discarded and
not retroactively certified.

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

工程指標應以「版本鎖定 OpenOCD 可證明的 Device/Driver/Operations → 通過精確 ICPN Software Qualification → Catalog 可見數量」為主要成果指標；24,051 等原始候選數是**獨立的背景庫存指標**，不得納入產品支援率分母或營運承諾。

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
