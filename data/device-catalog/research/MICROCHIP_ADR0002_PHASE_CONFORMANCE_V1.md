# Microchip Phase 1 / Phase 2 — ADR-0002 唯一規範對齊審查（2026-10-15）

## 唯一權威

依 [ADR-0002](../../../docs/adr/0002-openocd-software-qualified-catalog-visibility.md)
已採納的 2026-10-15 決議，Microchip **不另訂** Phase、研究等級、
軟體資格或 IC Selector 門檻；ST、NXP、Microchip 採相同的 canonical
Phase 1／2／3、逐欄位證據及執行資格邏輯。

| 判定維度 | 唯一可採用的規則 | 現有 Microchip 情況 |
|---|---|---|
| Phase 1 身分 | 單筆料號由官方完整商業 Exact ICPN、Base、URI、Scope 與捕獲時間達 `IDENTIFIED`；不以 CFG 作為**身分資格** | 有界 MCP 快照 **23,276 IDENTIFIED**；但**目前 Phase 1 工程交付目標 = 有 OpenOCD CFG 反向研究線索的凍結 2,563 筆** |
| Phase 1 欄位 | `VERIFIED/PARTIAL/UNKNOWN/CONFLICT/NOT_APPLICABLE`；每項來源 scope／版次／證據獨立 | 主資料多為 PARTIAL/UNKNOWN；N/A 必須有來源、不能憑猜測 |
| `INFORMATION_COMPLETE` | 所有必要欄位有精確適用證據並為 VERIFIED／有證據 N/A 才能標示；**不是 Selector 門檻** | **0**；不影響 23,276 身分有效性 |
| IC Selector visibility | Phase 1 `IDENTIFIED` 即有可查詢資格；CFG 是**工程選料範圍**而非額外身分 Gate | 本階段目標 **2,563**；main Microchip 0，#924 候選先交付 122，**目標剩餘 2,441**。其餘 20,713 是本次開發範圍之外的原廠身分資料，不因 CFG 未命中而失效 |
| Phase 2 `SUPPORTED` | 版本化 Provider + 精確料號 Silicon/CFG/Include/Driver/Bank/Security、宣告 Erase/Program/Read/Verify operation 與可追溯原廠 Programming 證據 | 尚無正式 Microchip software-qualified Programming Profiles；視為 `UNKNOWN`，不由 CFG 自動晉升 |
| Phase 3 `PASSED` | 指定 IC／Package、PPU、Site、Socket／Adapter 配置實機通過，且屬 Phase 2 子集合 | 尚無正式驗證的 Microchip Phase 3 PASS |
| Job／Batch | Phase 2 SUPPORTED + 對應已裝 Runtime + 供電、安全與必要硬體配置，**fail-closed** | 不能以 Phase 1 身分或 `no_mapping` 解鎖；#924 的 122 筆拒絕測試是初步實作 |

## Phase 1 本階段目標與分母

**本輪正式工程母體：五組 CFG 對應的 2,563 筆原廠精確商業料號**。
這 2,563 筆已通過原廠身份交叉驗證，但**不能因 CFG 存在而宣稱
Phase 2 `SUPPORTED`**。CFG 群組數：

- `pic32mx.cfg`：1,241
- `at91samdXX.cfg`：667
- `atsame5x.cfg`：354
- `atsamv.cfg`：175
- `atsaml1x.cfg`：126

**分母分離**：23,276 是觀測到的原廠 Exact ICPN 身分紀錄總量；
2,563 是本輪 Phase 1 開發交付目標；122 是第一批 Product Selector
實作提案（未合併）。若 122 筆全部上線，本輪尚餘 2,441 筆。
`INFORMATION_COMPLETE`、Phase 2、Phase 3 各自統計，不擅自升級。
這不是新的 Phase、P0/P1/P2 enum 或額外原廠身分資格門檻。

## 禁止再用的舊分類

原始研究來源與歷史 Hash 保留，但**正式的資料消費、API、UI、報表、Selector Gate
不得再使用 P0／P1／P2、S1／S2／S3 作為另一套資格狀態**。

舊版 2,437／126／20,713 是來源重播時的**歷史工作群組**，不是
三個 Phase 的狀態。**目前以五組 OpenOCD CFG 反查並由原廠證實的
2,563 筆為 Microchip Phase 1 工程目標**（2,437 + 126）；另外
20,713 筆是較廣的來源確認身分資料，但**不列為本輪必須交付的目標**。
CFG 線索只決定先做哪些料號，不能單憑 CFG 就判定身分或燒錄能力。
已凍結的 5 CFG、2,563 Exact ICPN 身分、Base、CFG 組合 SHA-256
`0c37ad68c1db0a4fb50ff5a1d229faaca0ee6eac44cfb9d9b7de4e8a931daf2a`
與原始資料仍保留，**禁止破壞證據以追求形式上移除舊欄位**。

本 PR 的 `microchip_adr0002_canonical_phase_contract_v1.py` 是
**Canonical 狀態投影與 CI Gate**：

- 只根據原始 manufacturer MCP 的 Exact ICPN 證據判定 Phase 1；
- 输出每個 ICPN 的 `phase1.identity_state`、`information_state`、
  五種欄位狀態，另列 `phase2.programming_state` 及
  `phase3.compatibility_state`，並獨立標記 `ic_selector_visible`；
- source 尚無獨立 Programming Qualification 時，Phase 2 一律 UNKNOWN，
  Phase 3 NOT_TESTED、execution false；
- 不輸出任何歷史研究優先級 enum，並維持 23,276 筆來源身分 distinct、
  SHA／Scope 與 deterministic replay；另使用凍結 2,563 筆建立
  **獨立工程目標追蹤報表**，並檢查全數確屬原廠已確認身分；
- 本投影**不是** Programming Profile 或可直接部署的 Product Catalog。

## 不能用文件冒充已完成的剩餘工程

1. **工程目標已定為 2,563 筆**：依五組 OpenOCD CFG 反向發現
   並核對官方 MCP 商業料號；`GET /api/devices/search`、IC Selector、
   Picker、`catalog_size`、`total_count`、分頁與廠商數量，應按
   **本階段已實際上線的 Phase 1 ICPN** 準確呈現。
   目標是分批完成 2,563 筆，不要求這個階段匯入整個 23,276
   身分來源快照。單筆可見性仍只能看 `IDENTIFIED`；CFG 只是
   規劃目標條件，不得拿來宣稱已確認料號在其他研究範圍內不合格。
   先建立 source-locked 持久化資料，不能把 90 天 CI artifact 當永久庫。
2. **#921／#924 為前置增量，不能被誤認為權威**：#921 的 PDF
   訂購碼六欄位補強不授予 Phase 1 身分，因原始 MCP 身分在先；
   #924 的 122 筆只是第一次功能性上線增量；依本次凍結目標，
   **2,563 − 122 = 2,441** 筆仍待完成本階段 Selector 工程。
   其餘 20,713 筆保留原廠身分證據，既不當成這次未完成量，
   也不可因 CFG 不在這五組而撤銷有效 `IDENTIFIED`。
3. **Phase 2 驗收必須獨立建模**：從 Phase 1 的同一 Exact ICPN
   store 選取候選，逐件保存 Provider 版本、Silicon／Revision、
   target/flash bank／driver、幾何與安全、操作範圍與原廠原始證據；
   不可把 CFG-only、Core 家族類推或 `no_mapping` 當 SUPPORTED，
   也不可借用歷史 P0/P1 優先序。Phase 2 即使 UNSUPPORTED，
   也不撤銷有效 Phase 1 IDENTIFIED 或在 Selector 中消失。
4. **五種欄位狀態**：所有 Microchip field adapter／validator
   都必須接受有證據的 `NOT_APPLICABLE`，但不得以「尚未找到」
   當成「原廠證明沒有」；VDD、VDDIO、VDDA／VDDANA 不得互代。
5. **ADR 文件校正**：舊 Decision summary 流程圖中的
   `SUPPORTED-only` 與已採納的 Phase 1 visibility 決議矛盾；
   本 PR 只修正那段過時摘要，沒有改變規範政策。

## 驗收與限制

CI 同 job 從原廠 MCP/DFP 完整重播結果，
對原始 23,276 筆做來源與 Canonical 資料驗證，並將其中凍結
**2,563 筆**當作目前 Phase 1 交付目標，核對 CFG／Exact ICPN／Base
成員 SHA、欄位狀態與 `INFORMATION_COMPLETE` 一致，
並執行負向測試保護 no-source／假資料／Phase 2 越權。

**此 PR 不合併 #921/#924、不寫 Production Catalog、
不部署 Control Station、不提高任何 Microchip SUPPORTED 數量。**
原始資料、舊歷史報表與全部未完成的 IC 欄位缺口都應保留。
