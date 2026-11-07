# PLASMA Site 2 — 2026-11-07 首次真實 Flash PASS（固定證據）

本資料夾記錄 PYNQ-Z2 Site 2 的 STM32F103C8T6 **一次真實 Flash、Readback Verify 與 SAFE_OFF PASS**。既有 GitHub Actions ZIP 是原始容器，但有保存期限；這裡的 evidence.json 固定了來源、Run/Job、原始 stdout（除受隱私範圍限制的 Preflight 已裁剪）、SHA256、以及 FAIL → 唯讀對帳 → PASS 的實際順序。證據固定不代表另一次操作。

## 最終驗收事實

| 欄位 | 觀測值 |
| --- | --- |
| 實機 Runner | SWPC-plasma-codex；既有非 root Path 2 operator-cli |
| 原始執行 HEAD | ad439285a0e3552634f7679d341538d4be1128f1 |
| 真實 Flash Run | https://github.com/physicslu/plasma/actions/runs/42356019198 |
| Flash Job | job-20261107-083434-0c00decf |
| SITE / ICPN | Site 2 / STM32F103C8T6 |
| Image／Readback SHA256 | 8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d |
| 完整 Readback | 18768 bytes；Flash result PASS、attempts=1、submission_count=1 |
| SAFE_OFF | true |
| 結束後 | Site 2 Idle、0 個 OpenOCD process、沒有 Seal/Admission record |
| Active OPF Set SHA256 | b82ce5fd0725dacdd02a3805168e847b190841c95887ba2c567761a48024e393 |
| 原有 OpenOCD binary SHA256 | b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861（未更換） |
| 新版 Admission SHA256 | 3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b |

## 證據鏈與失敗紀錄

1. https://github.com/physicslu/plasma/actions/runs/42348102004 — Z2 唯讀根因鑑識：舊 Engine Admission 仍引用已移除的 DEVMEM_INDEPENDENT_IMAGES，受保護 Root 與 Git 相符。
2. https://github.com/physicslu/plasma/actions/runs/42354483913 — 新 immutable Engine 已發布但尚未選用；二進位 SHA 與既有一致。
3. https://github.com/physicslu/plasma/actions/runs/42354639724 — 初次 Engine SWITCH 回傳 NameError，當時不能認定切換失敗或成功；沒有重試。
4. https://github.com/physicslu/plasma/actions/runs/42354798488 — 唯讀對帳證實 Engine Selection 已切為 NEW，且原 binary 與 Tcl 不變；沒有再次切換。
5. https://github.com/physicslu/plasma/actions/runs/42354899860 — Site 2 Gateway/Worker/FPGA/Image/Boot/Engine Readiness，無已知 blocker。
6. https://github.com/physicslu/plasma/actions/runs/42354991188 — 實機 Root Admit PASS → Revoke PASS，未留 Admission record；未操作 DUT。
7. https://github.com/physicslu/plasma/actions/runs/42355729976 — 已啟用 OPF Set SHA 唯讀取證；0 Active Job／Idle。
8. https://github.com/physicslu/plasma/actions/runs/42356019198 — 真實 REST 單次 Flash Job PASS／Readback Verify／SAFE_OFF／Idle 收尾。

## 永久化與驗證界線

- evidence.json 中每個 run 的原始 stdout 雜湊來自原 Runner Receipt；每個 ZIP SHA256 是從實際下載的 GitHub Actions Artifact 位元組另行核算，非猜測或由 Git Commit 推導。
- 對於一般回執，evidence.json 同時保留 original_stdout_line（未改動的回執行）與 typed_evidence，可由 test_site2_first_flash_evidence.py 重算 SHA256（加一個實際 newline）驗證；這可在 GitHub Artifact 到期後仍核對回執。
- 唯讀 Preflight 的 original_stdout_line 已刻意**不納入公開 Git**，以免固化測試裝置 ID、服務 PID 等細節；保留原 stdout SHA256、選定安全欄位、Artifact SHA256 及原 Run 連結。此項不是 byte-complete 的永久回執，不能聲稱完整原始機器識別已固化。
- Run #42354639724 的命令有真實 NameError，僅標記失敗及受控唯讀對帳的連結，不把其失敗當成二次操作成功。
- Runner 內通用 physical_hil=NOT_VERIFIED 是 Dispatcher 不具資格判定能力的提示；真正的 Site2 Flash PASS 必須引用 Runtime Job 的終態與 Readback/SAFE_OFF。這裡**只認定單一 Site、單一 IC、單次 Job**，不是 8 Site 同步或正式生產資格。
- GitHub-hosted mock/CI 不等於再次執行 HIL；合併此資料夾不會進行部署或 Flash。後續 Python Admission／OpenOCD Build 完全解耦另見 Issue #1340。

## Path 2 三入口

使用 docs/deployment/plasma-program-cli.md 所述通用 Bundle CLI；它們**不是**本次原始實機驗收已測過的相同腳本版本。新入口需以其自身 CI 與未來特定批准的 Work Order 驗證。
