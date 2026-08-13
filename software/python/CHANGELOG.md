# Plasma 版本紀錄

## 未發佈 — 2026-08-13

### Web Mock 整合

- Web Console 改為呼叫 Python REST Gateway，不再以瀏覽器 timer 模擬工作進度。
- Gateway 加入 CORS preflight 與可設定的 allowed origin。
- Gateway JSON body 上限調整為 24 MiB，可容納 16 MiB firmware 的 Base64 payload。
- 新增 Gateway → Plasma v3.1 TCP Server → `MockInterface` program/cancel 端對端測試。
- Python 自動測試由 66 項增加至 69 項。

## v0.3.1 — 2026-08-13

### 改善

- 驗證 `JobRequest`、`job_id`、保留 metadata、timeout/retry 數值及通訊欄位型別。
- 阻擋 `job_id` 路徑穿越與 read section 檔名正規化碰撞。
- 等待全域 semaphore 的工作可立即取消。
- Channel Manager 關閉時會取消執行中與排隊中工作。
- `safe_shutdown()` 失敗不再產生假成功，改回報 `E5002 INTERFACE_FAILURE`。
- Mock 在操作前檢查位址範圍，拒絕未知設定，並複製故障注入資料避免污染呼叫端。
- 協定新增 `firmware_size` 型別／BINLEN 與 SHA-256 格式驗證。
- Server 將錯誤數值與型別穩定分類為 `E1001 INVALID_ARGUMENT`。

### 測試

- 純軟體自動測試由 51 項增加至 66 項。
- CLI program/read 端對端測試通過。
- CLI `Ctrl+C` 遠端取消與通道恢復測試通過。

### 尚未完成

- OpenOCD + STM32F103C8T6 實機測試。
- PYNQ-Z2／FPGA register map、AXI 與雙通道硬體測試。
- Web 身份驗證、TLS 與量產權限模型。
