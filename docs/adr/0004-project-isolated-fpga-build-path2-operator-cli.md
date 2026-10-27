# ADR-0004 — 專案獨立的 FPGA Vivado Build 與 Path 2 operator-cli 標準

> **Status: Accepted (Owner architecture decision, 2026-10-27)** — 此 ADR 目前位於 Draft PR #1189；在合併 main 前尚非已部署的可信 Dispatcher 改版，也不代表 SWPC 已完成新 MPE Build。
>
> **Scope:** 所有後續 PLASMA 新增或重大改版的可交付 FPGA Image／Board 目標；新 MPE 為首個採用者。僅定義建置與驗收標準，不擴張硬體／Root 權限。

## Decision

1. **每個 Image family × Board target 有獨立的可重現 Vivado Project。** 將來源 RTL、必要 IP/BD、pin/XDC、時脈／Reset、PS7/AXI 整合、建置 Tcl、板卡版本與 HWH/Bitstream 驗證器歸在 `pl/projects/<project-name>/`。共用 RTL 或共用工具可以重用，但不得把特定 Project 的 Tcl、ABI、XDC、Artifact 檢查硬編碼成全系統入口。獨立 Project 並不代表每個 SWD/SPI Engine 都要有獨立 Bitstream；產品可在單一 Universal Image 中整合多個 Engine。
2. **SWPC 正式、可重現的 FPGA Host Build 採 Path 2 `operator-cli`。** 由現有可信 Dispatcher、Owner 批准的 SHA 固定 Work Order 呼叫受版控且受審查的 Python 入口；該入口啟動所選 Project 的 Vivado Tcl，不經固定的 F1-B Build Registry／Stage／project allowlist。建立、驗證、執行腳本均不得暗藏自動 Download、FPGA Manager、MMIO、DUT、OpenOCD 或 Flash 操作。Path 3 可進行 Owner 核准的工程實驗，但不取代這條可重現的 Path 2 建置／資格流程。
3. **建置與產品驗收分層。** 必須記錄 exact PR HEAD/source SHA、Work Order digest、Toolchain／License 前置檢查、Board Files revision／hash、實際 RTL/XDC/Tcl/BD 輸入、Vivado process exit、Synth/Impl/Route、WNS/TNS/WHS/THS、check_timing、DRC／Methodology、BIT/HWH（需要 BIN 時也納入）、每個產物 SHA256、Image Manifest 與失敗日誌。任何缺失、CI 假資料、Mock Artifact 或只通過 exit 0 均不得標示 Build Qualified。HWH 必須與實際 ABI、Site、Address、Pin、Clock/Reset 配對。
4. **不建立第二個固定建置框架。** 建議一個可重用的執行薄層處理環境、工件與證據；每個 Project 自有 Tcl／Manifest／Verifier。不得讓新 Project 引用 `pl/projects/z2-fixed-unified-site1/` 的專屬 Tcl、HWH verifier 或部署資產，也不得藉由複製／重新命名 F1-B 固定檢查器當成通用化。
5. **Build != Deploy。** Path 2 `operator-cli` Build 僅使用 SWPC 非 Root Worker 已有的 OS 權限；Image Load、FPGA Manager、PS MMIO、DUT 供電與 Flash 燒錄仍受各自獨立的 Owner Gate、Root Guard、Hash、Boot/Ownership、Golden Recovery 與 HIL 控制。不得因 Build PASS 自動接續 Download／Test。
6. **Fail closed。** 新 Project 缺少受審查入口、Project Tcl、可驗證來源或合格產物時回報 `NOT_RUN`／`FAIL`，不能 fallback 到 F1-B Engine、舊 FPGA Build Registry/Stage 或任何單 Site Image。

## 現有 F1-B 專屬 Build Engine：限期遷移、未完成前保留

**標的：** `pl/projects/z2-fixed-unified-site1/`、`scripts/plasma_vivado_host_build.py` 中 F1-B 專屬執行路徑，以及 Dispatcher 的 `vivado-host-build` 固定 Site1 Project 投影／Build Registry/Stage 入口；不包含應保留的通用 License 診斷、Board 檔案來源證據、Root/Golden Recovery 或歷史合格 Build Artifact。

**目前狀態：** `F1B_BUILD_ENGINE_RETIREMENT_PENDING`。不得因本 ADR/PR 提交就刪除尚有使用者或復原責任的舊建置途徑，也不得聲稱已關閉原 `vivado-host-build`；新 FPGA 專案從本決策起**禁止新增 F1-B 依賴**。

**退役進入條件（均需具體證據）：**
- 新 MPE 獨立 `pl/projects/z2-mpe-dual-site/` 具完整可重現 Project Tcl/PS7/AXI/XDC/Manifest／專屬 verifier；在 SWPC 使用核准的 **Path 2 `operator-cli`** 完成真實乾淨建置及 BIT/HWH/DRC/Timing/Hash 驗收。
- 完成新 Project Host-only CI、Source/Dependency guard（含 Legacy negative tests）；核對 Dispatch 到 Work Order 及版本 SHA、執行記錄與中止行為。
- Repository-wide 反向相依盤點涵蓋 Launcher、Workflow、Scripts、Manifest、Device Image、文件、測試與已安裝 Worker；列出需遷移／保留的所有 F1-B consumer。
- 在變更可信 Dispatcher 行為之前，移轉正式建置使用者並通過新舊隔離驗證；保留現有 Golden Image／Root Recovery 的獨立可用性與歷史證據。
- 獲 Owner 對 **F1-B 專屬 Engine 退役 PR** 的 Gate 2 核准後，移除正式入口、舊 project selector、task/registry 與隱含 fallback；不再允許新 Work Order 選用 F1-B 專屬 Engine。舊資料可留在標記 `HISTORICAL / RETIRED / DO NOT USE` 的唯讀歷史區，並用 CI 阻擋新來源引用。

**退役與 MPE IP 的正式取代是不同決策。** MPE 的 SWD Driver/IP/API/文件退役還需另外驗證真實雙 Site DPIDR、OpenOCD、PS MMIO 與跨 Site 獨立性。本 ADR 不授權提前撤除任何運作中的 Hardware Safety/Recovery 路徑。

## Migration & consequence

- 新 MPE 建置入口、Project Tcl／Verifier／Image Manifest **尚未實作／Host Build NOT_RUN**；所以目前僅能標記 `BUILD_STANDARD_RECORDED`。
- 固定 `vivado-host-build` 限於既有 F1-B 歷史／遷移用途；不擴充其 Project allowlist，也不拿它建新 MPE。
- 現有 Path 2 `operator-cli` 以 SHA 固定 Python script、`scope: guarded-hardware` 與受限 `timeout_seconds` 運作；若實際 Vivado 全量建置所需時長超出現有 1800 秒上限，先提出安全且可驗證的受審查延長／續跑方案，**不能分段偽造 Build PASS**。
- 此 ADR 決策與 `docs/adr/0003-runtime-fpga-driver-reconfiguration-boundary.md` 的 Image Runtime 決策正交：定義 Build 路線，不允許 Runtime 自動 Reload。
