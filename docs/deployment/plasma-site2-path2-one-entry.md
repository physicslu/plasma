# PLASMA Site 2 — Path 2 一鍵部署／診斷／燒錄

這是現有 Issue #981 owner-authenticated Path 2 operator-cli 的三個單一操作入口，不是新的 Dispatcher、Runner、root shell 或通用燒錄服務。限 PYNQ-Z2／Site 2／STM32F103C8T6 開發模式。每個操作獨立執行，不會把「部署成功」自動串接成燒錄。

## 三個入口

| 指令 | 執行內容 | 寫入範圍 |
| --- | --- | --- |
| python3 scripts/plasma_site2_path2_ops.py deploy --source-sha SHA --approved-once | 沿用既有 opf_site2_joint_acceptance：Doctor → Active Asset → 必要時 Bootstrap B1/B2/B3 → Doctor。OPF 已 Active 則 no-op | 只處理受審核的 OPF Bundle，無 FPGA Reload、Engine 更新或 DUT |
| python3 scripts/plasma_site2_path2_ops.py diagnose --source-sha SHA | Site 2 REST／FPGA／Engine／OPF 唯讀 preflight | 無寫入，不執行 Admit、SWD 或 Flash |
| python3 scripts/plasma_site2_path2_ops.py flash --source-sha SHA --approved-once | 沿用既有單次 REST flash_cycle + Readback Verify + SAFE_OFF | 只允許明確核准的 Site 2 目標及已固定的 Firmware/Asset Set |

SHA 必須替換為執行當下確切候選 Commit SHA；內部檢查 git rev-parse HEAD。--approved-once 只防止 CLI 誤觸，不取代 Owner 透過 Issue #981 發出的具體 Gate 1 授權。既有 Gate 1 批准首次燒錄，不代表授權未來任意重複燒錄。**合併後不能把已關閉 PR #1338 的 candidate SHA 當作往後持續運作的來源。** 主線 Path 2 Work Order 請使用 pr_number=0，並在 Work Order JSON 中省略 source_sha 屬性（目前 Dispatcher 會由受信任的 main 事件帶入），但 argv 仍要提供當次確切 main HEAD 給 --source-sha。若 main SHA 與核准時不符，source_guard 應拒絕執行；不得自行改成舊 PR 的 source_sha 欄位繞過。

## Path 2 Work Order 固定欄位

每次從既有 Issue #981 傳送一個 source-pinned Work Order：

- schema: plasma.development.work_order.v1
- execution_path: path2-cli
- capability: operator-cli
- scope: guarded-hardware
- script: scripts/plasma_site2_path2_ops.py
- argv: [deploy|diagnose|flash, --source-sha, EXACT_SOURCE_SHA]；部署與燒錄再附加 --approved-once
- source_sha: EXACT_SOURCE_SHA，並依既有規則選擇當下有效且已核准的 PR/main 來源
- objective、acceptance：清楚限定本次操作、目標 Site、版本、預期 Artifact SHA、權限及失敗停機條件
- timeout_seconds: 使用目前 Dispatcher 支援的 bounded 參數，例如 900（不可當成允許自動重試）

**安全設計**

1. 部署不可憑空複寫未知 Active Set。沿用舊版 Gen7 → 新 OPF B1/B2/B3 的現有受審核路徑；若已符合當前 OPF，直接 ALREADY_ACTIVE_NO_REDEPLOY。發生模糊寫入或失去 Receipt，停止並人工對帳，不重送。
2. 診斷預設嚴格唯讀，正常結果也不代表物理 SWD／Site Lock／DUT 已 PASS。要進行 Root Admit/Revoke 使用既有獨立受控腳本，不能偷偷放入無狀態診斷。
3. 燒錄維持固定 STM32F103C8T6、Site 2、18768 Bytes 韌體（SHA256：8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d）、Active Set（SHA256：b82ce5fd0725dacdd02a3805168e847b190841c95887ba2c567761a48024e393）。發出一次 POST 後若狀態 UNKNOWN，不得自動再次提交；保留 Job ID 做唯讀對帳。
4. 所有真正電氣／Site Ownership／OpenOCD 驗證仍由 Z2 上既有 Runtime、Site Worker、Root Guard 執行；SWPC 只呼叫高階動作。沒有重新編譯 OpenOCD、沒有重載 FPGA，也沒有重新安裝 Driver。
5. 三入口是 Site 2 PoC 封裝，不表示 8 Site 同時燒錄、NXP/Microchip、多種 Flash Layout 或生產資格已被驗證。

## 已完成的首次實機證據

不可變的原始來源 HEAD：ad439285a0e3552634f7679d341538d4be1128f1（2026-11-07）。唯一真實 Flash Job：job-20261107-083434-0c00decf。18,768 Bytes Readback SHA256 與 Image 完全一致，SAFE_OFF=true，Site 2 恢復 Idle，無殘留 Admission Record、Seal 或 OpenOCD Process。

原始 evidence.json 與 Run/Job/Artifact SHA 固化於 docs/evidence/site2-first-flash-2026-11-07/，詳見該資料夾 README。新三入口的 Host-only CI **不等於**再次對 DUT 進行驗證。

## Gate 條件

PR #1338 Gate 2 合併需確認最新 HEAD 的 CI、Rulesets、Reviews、Threads、Mergeability；合併僅改原始碼，不授權部署或重送 Flash。
