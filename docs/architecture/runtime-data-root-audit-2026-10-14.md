# PLASMA Runtime Data Root 架構稽核 — 2026-10-14

**稽核基準：** main `130ba7a6f60a08c858ffe087b2d5a5b437bb605c`。**類型：** 程式碼／CI／部署設定靜態稽核。此 PR 只建立稽核報告，未執行外部部署、沒有修改 runtime 程式或完成 HIL。請勿把靜態風險視為已驗證的線上故障。

**已知事故與已完成修正：** #827（2026-10-12）為 IC Support 加入 `PLASMA_IC_SUPPORT_ROOT` 與啟動檢查；#844（2026-10-13）新增 NXP manufacturer loader，重新使用 `__file__.parents[3]`，在 Render 非 editable 安裝發生路徑錯誤；#873（2026-10-14）已修正該 NXP loader，加入安裝環境測試及 NXP 查詢 smoke。NXP #873 不需要重複修正。

## 1. 現行 Data Root 稽核矩陣

| 分類 | 元件 | 路徑機制與靜態證據 | 評估 |
|---|---|---|---|
| 已有保護 | `plasma_web/device_catalog.py` | `PLASMA_DEVICE_CATALOG_MANIFEST` 優先；Render `render-start.sh` 設定明確原始碼 checkout manifest 並驗證 SHA-256、Git blob、row counts；未設定時仍會從模組位置 fallback。 | Render 已正確配置；非 Render 已安裝套件應強制提供 manifest path。 |
| 已有保護 | `plasma_core/ic_support.py` | `PLASMA_IC_SUPPORT_ROOT` 優先；#827 修正後 Render 會驗證 profiles/bindings，缺資料 fail-closed。 | 保留既有有效的配置契約。 |
| 已修但與目錄形狀耦合 | `plasma_web/nxp_manufacturer_device_evidence.py` | #873 以 `default_catalog_manifest_path().resolve().parents[3]` 決定 repository root；在標準 `data/device-catalog/production/icpn-v1-manifest.json` 佈局正確。 | 此為目前 NXP 問題已解決的證據；將來 manifest 任意搬移後推算不具普遍性。暫不更動。 |
| **P1：展示資訊缺失風險** | `plasma_web/backend_candidate_registry.py` | `ROOT=Path(__file__).resolve().parents[3]`；default registry 使用 `allow_missing_sources=True`。在已安裝套件無研究檔時會直接回傳空 Candidate Registry。 | 可能使 **ST H5 190 + C5 172** source-only 候選從 UI 消失，不變更 Production backend mapping；不是 HIL 風險或已確認 Render 故障。 |
| **P1：展示資訊缺失風險** | `plasma_web/openocd_provider_registry.py` | 同樣的 module-relative `ROOT`；任何 required source 檔不存在即回傳 `None`，API `backend_providers=[]`。 | 已安裝環境可能看不到來源已鎖定的 OpenOCD Provider 版本／Build evidence。不得錯誤宣稱可燒錄。 |
| **P1：來源描述缺失風險** | `plasma_web/backend_source_reference.py` | `load_pinned_upstream(root=ROOT)` 以 module-relative ROOT 讀 `release/openocd.json`；`FileNotFoundError` 回傳 `None`。 | existing mapped IC 的 source version／commit 可能變 null；source provenance 變弱，不應混同 target mapping 無效。 |
| **P1（啟用前）：執行阻斷風險** | `plasma_interfaces/kl25_openocd_plan.py` | `_repo_root()=__file__.parents[3]` 讀 `data/ic-support/benchmarks/nxp-kl25/backend-implementation-lock.json`。 | Installed wheel 下可能找不到 lock 並造成 Plan compile 失敗。目前 `execution_router.py` 註明 default runtime 沒有 KL25 Production operation admission；須在該 execution gate 開啟前解決。 |
| Merge Gate | Draft PR #872 `nxp_phase1_information.py` | PR 分支已改為從 Production Manifest 推算 root。 | 合併前以最新 main 和 non-editable install 執行完整 Source/Selector regression；本文件不合併 #872。 |

**判讀**：本次沒有取得 Render 的 H5/C5 實際 API 完整回傳，也沒有執行 KL25 硬體程式。表中的 P1 代表應驗證的程式路徑風險，**不是已確認生產事故**。

## 2. 回歸缺口

- #827 的 `PLASMA_IC_SUPPORT_ROOT` 只約束 IC Support；新增 manufacturer loader 未遵守同一原則，形成 #844 → #873 的回歸。
- 之前的來源樹／editable 測試容易讓 `__file__` 正好指到 checkout root，漏掉安裝套件的不同 layout。
- #873 專用 CI `render-nxp-selector-evidence-root.yml` 已使用非 editable `pip install software/python`，但主要驗證 NXP exact 與 existing manufacturer evidence，**沒有涵蓋 H5/C5 三個 source registry 和 KL25 lock**。
- `render-start.sh` 目前驗證 STM32F103C8T6、`NXP` 有搜尋結果、`MCXA132VFM` exact profile；`NXP` startup smoke 僅要求結果存在，未要求精確 total_count=224；也不驗證 H5/C5 source-only evidence。
- Optional-by-design 的 Slim PPU fallback（隱藏 optional research metadata）與 Full Render 遺漏來源造成的誤降級，目前缺少部署情境分界。

## 3. 新架構契約（建議，尚未實作）

**第一原則：資料根、檔案完整性及授權三者相互獨立。** 取得正確路徑不等於來源可信；來源可信亦不代表允許執行燒錄。

1. 建立單一受驗證的 `RuntimeDataPaths` resolver；由部署設定提供 Catalog manifest、IC Support root、research evidence root（具體設定鍵需 ADR 決定）。正式 installed runtime **禁止以套件 `__file__` 推算 repository root**。
2. Catalog manifest 與可執行 IC Support lock 視為 Required，缺失或 hash 不符 fail-closed；保留 #827 的環境變數相容性。研究／來源版本證據依部署 profile 定義「Required in Full Render」或「Legitimately omitted in Slim PPU」，不得將缺檔錯誤展示成 `unsupported/no_mapping`。
3. 來源檔必須繼續使用 Git blob/SHA256 或現有相當之鎖定證據；版號、裝置身分、Backend Mapping、Job/Batch Admission、PPU/Socket/HIL 狀態完全獨立。
4. 修正 H5/C5 candidate/provider/source-reference 三個讀取器；為缺失來源建立明確、可稽核的 metadata availability 狀態，不在 slim runtime 捏造 source 或能力。
5. KL25 鎖定檔應由既有 `PLASMA_IC_SUPPORT_ROOT` 提供，並在 compiler 能產生 operation 計畫之前驗證。無 lock 絕不得 fallback 或執行。
6. 保持 Production 4,853 / NXP 224 exact identities；Research-only 277 不加入 Selector；不動 OpenOCD qualification。

## 4. 分層 CI 與 Release Gate

| 測試配置 | 驗收 |
|---|---|
| Source checkout + editable | 保持現有 ST / NXP / Catalog／KL25 回歸 PASS。 |
| Installed wheel + explicit roots | `NXP` total_count=224，`MCXA132VFM` exact manufacturer evidence，`STM32F103C8T6` selected profile 完整。 |
| Installed wheel + full Render evidence | `STM32H503CBT6` + `STM32C531CBT6` 的 `backend_candidate`、`backend_source_reference`、`backend_providers` 存在且 immutable source-only；依然 `no_mapping` / no HIL。 |
| Installed wheel + intentionally slim runtime | 可合法省略 research-only files，但必需 Catalog／executor locks 不可默默缺失；回傳可判斷 metadata missing state。 |
| Invalid root / source tampering | 明確 fail-closed 或依 profile 回報缺證據；絕不歸類為已支援燒錄。 |
| Installed KL25 plan compiler | 鎖定檔從 IC Support root 取得，digest 失敗 negative，沒有 execution admission 的情境絕不提升資格。 |
| Render startup + public smoke | 除 ST/NXP 搜尋以外，依 full profile 要求 source evidence 的 H5/C5 欄位存在；版本和本次部署 commit 關聯。 |

## 5. 推薦實施批次

- **A — 顯示資料路徑修復（優先）**：修正三個 H5/C5/OpenOCD 讀取器及 non-editable CI；不改 Catalog 和 Programming。
- **B — KL25 execution readiness**：鎖定檔改接 IC Support root，增加安裝包與負測試；維持執行預設不開放。
- **C — 公用基礎建設**：統一 `RuntimeDataPaths`、部署 profile schema、可觀測的 missing-state 與 lint/CI 條件，避免後續每個 manufacturer 自訂 root。
- **D — PR #872 獨立驗收**：獨立 rebase、專用 CI、合併核准與部署核准。

**結論：** #873 已修，不需重複動作；需處理的是顯示資料缺失的潛在靜默降級與 KL25 lock 的安裝包路徑，並將 #827 的領域修補上升為全專案的共同 Runtime Data Root 契約。**本稽核 PR 僅供審查，沒有任何執行程式改動。**
