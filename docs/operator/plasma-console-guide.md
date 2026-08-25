# Plasma Console Operator Guide

本指南說明目前 Plasma Web Console 的 PMode（量產模式）與 EMode（工程模式）操作契約。它是操作摘要；詳細資料模型與 API 仍以 [Batch Domain Model](../architecture/batch-domain-model.md)、[Web REST API Contract](../architecture/web-rest-api-contract.md) 與 [Gateway Communication and Recovery](../architecture/gateway-communication-recovery.md) 為準。

## 模式與執行鎖定

- **PMode**：跨 Facility／PPU 選定 Production Set，再執行一個 server-side Batch。
- **EMode**：針對單一 PPU 的 Sites 進行工程操作、Mock 設定、診斷與 Gateway 設定。
- Batch 在 `QUEUED`、`RUNNING` 或 `STOPPING` 時，模式切換與 Batch membership 必須鎖定。
- 只有在所有已接受 Job 都被觀察為 terminal，且 Batch 已進入 terminal state 後，才可解除模式鎖定。
- 執行中只提供 whole-Batch **ABORT**；operator ABORT 會取消該 Batch 所有仍在執行的 Job。

## 建立 Batch

1. 勾選要處理的 Site。`SITES` 顯示目前 Batch 所選的 Site 數，不是系統拓撲總數。
2. 選擇 Target IC。真實 provider 執行時必填；Mock provider 可以使用 `MOCK-IC`，不代表真實 IC 已通過驗證。
3. 選擇 Programming Image。Program／Verify 對真實 provider 必須有 `Image + binary` Programming Asset；Mock 可由 Default Image Size 產生 Synthetic Image。
4. 選擇 E/P/V/R 操作：Erase、Program、Verify、Read。
5. 設定 Batch Policy：
   - `Repeat`：每個已選 Site 預計處理的 IC 次數；目前 Mock 用它模擬逐顆 IC 交替。
   - `Site Retry Limit`：可信任的單一 Site 操作失敗後的 Job retry；不是 Gateway 通訊 retry。
   - `Stop Policy`：retry-exhausted FAULTED Sites 達門檻時停止後續 Batch 工作。
6. 檢查 `BATCH READY` 後按 **START PROGRAMMING**。

## Batch Summary

| 指標 | 定義 |
|---|---|
| `SITES` | START 時凍結的已選 Site 數。 |
| `TOTAL IC` | `SITES × Repeat`，即 Batch 預計處理的 IC 數。 |
| `PROCESSED IC` | `PASS + FAIL`，即已有可信任燒錄結果的 IC 數。基礎設施 `ERROR` 不可冒充 IC FAIL。 |
| `PASS` | 完整 Batch round 成功的 IC 數。 |
| `FAIL` | 完整 Batch round 的可信任 IC／Site 燒錄失敗數。 |
| `YIELD` | `PASS / (PASS + FAIL) × 100%`。尚未有結果時顯示 `—`，不是 0% 或 100%。 |
| `BATCH TIME` | Batch 從開始到現在或 terminal 的經過時間，格式 `HH:MM:SS`。 |

`RUNNING SITES` 仍可用於 Live Site Status，但不是製造數量 KPI；上方 Batch Summary 以 `PROCESSED IC` 表示實際已處理數。

## Live Site Status

- Facility、PPU 與 Site checkbox 決定**下一個** Batch 的 membership。
- Facility checkbox 對該 Facility 內全部 PPU／Site 全選或取消；PPU checkbox 對該 PPU 全選或取消。
- START 後 membership 凍結；執行中 checkbox disabled。
- `RUNNING` 狀態燈以一秒週期 pulse，提醒 operator 尚有工作進行；狀態判定仍以 server response 為準，動畫不是計時器或成功證據。

| Site 狀態 | 意義 |
|---|---|
| `READY` | 可加入下一個 Batch。 |
| `RUNNING` | 已接受的 Job 尚未 terminal。 |
| `PASS` / `SUCCESS` | 該 Site 的計畫 round 已完成。 |
| `FAULTED` / `FAIL` | Job 有可信任的 DUT／Site 失敗結果。 |
| `ERROR` | Gateway、PPU 通訊或 runtime 基礎設施異常；不計入 IC FAIL／Yield。 |
| `STOPPED` | 因同 PPU 基礎設施錯誤或 Batch stop policy 未繼續執行；不是 IC FAIL。 |
| `CANCELLED` | operator ABORT 或 cancel 已完成。 |

## Gateway timeout 與 retry

EMode 的 `Settings -> Gateway` 設定 PMode／EMode共用政策：

- Request Timeout：1–120 秒，預設 10 秒。
- Retry Count：0–10 次，預設 3 次。
- retry backoff：1、2、4 秒，後續維持 4 秒。
- 每個 Batch 在 START 時凍結 policy revision；修改只影響下一個 Batch。
- Job submission 不會因不確定結果而自動重送；已取得 Job ID 後的 status observation 才使用 Gateway retry，避免重複建立 Job。

## 通訊異常與復原

1. 查看 Site 的 `communication_state`、Batch error 與 Engineering Job Log，區分 `FAULTED` 和 `ERROR`。
2. 單一 PPU 的 Gateway retry 用盡時，只停止並取消該 PPU 在目前 Batch 的 active Jobs；其他 PPU 繼續。
3. 如果整個 Batch runtime 發生無法歸屬單一 PPU 的例外，或 Stop Policy 被觸發，才可能停止整個 Batch。
4. 若畫面仍顯示 busy，不可只靠重新整理強制解除。先確認 Batch terminal；必要時按 whole-Batch ABORT，等待 accepted Jobs terminal。
5. 重新連線只重建觀察能力，不可把未知中的 Job直接當成失敗或成功。

## Mock 的限制

Mock 支援 Synthetic Image、可重現的操作 failure profile 與 8 Facilities × 4 PPUs（每個 Facility 的 Site topology 依序為 2／4／6／8）。Mock Settings 的 `error_rate_per_mille` 注入的是 E/P/V/R 操作失敗，不是 Gateway 斷線；目前 UI 沒有獨立的通訊中斷注入選項。Gateway timeout/retry 仍作用於實際 provider request，自動測試會以可控 provider fault 驗證通訊復原。

Mock PASS 只證明軟體流程與 contract，不能宣稱 OpenOCD、Z2/FPGA 或真實 IC programming 已驗證。
