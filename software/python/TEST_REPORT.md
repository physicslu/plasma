# Plasma v0.3.1 pytest 與 Web Gateway 測試報告

## 執行摘要

| 項目 | 結果 |
|---|---|
| 執行日期 | 2026-08-16 |
| Python | 3.12.13 |
| 測試執行器 | `pytest 9.1.1`；相容收集既有 `unittest.TestCase` |
| 測試數 | 75，另有 8 個 subtests |
| 通過 | 75；8 個 subtests 通過 |
| 失敗 | 0 |
| 錯誤 | 0 |
| 跳過 | 0 |
| 最終執行時間 | 6.37 秒 |
| Web Gateway REST API | 5/5 通過 |
| Web → Gateway → TCP Server → Mock E2E | 2/2 通過 |
| CLI 進度端對端 | 通過 |
| CLI `Ctrl+C` 取消端對端 | 通過 |
| Editable install／console entry | 通過 |
| pytest-cov line coverage | 83%（1795 statements，302 missing） |

執行指令：

```bash
./scripts/run_tests.sh
```

結果：

```text
75 passed, 8 subtests passed in 6.37s
```

## 已驗證

- Web status 查詢、Firmware program submission、verify 缺少檔案拒絕、遠端 cancel
  與 CORS preflight。
- 真實 HTTP Gateway → Plasma v3.1 TCP Server → `MockInterface` 的 program
  `erase → program → verify`、進度、成功結果與安全取消。

- v3.1 frame encode/decode、fragmented read、半包與 checksum。
- `firmware_size`／BINLEN 一致性、SHA-256 格式與內容驗證。
- 路徑型 `job_id`、保留 metadata 覆寫與 read section 檔名碰撞拒絕。
- boolean channel ID、錯誤 retry/timeout 值與非 boolean wait flag 的穩定錯誤分類。
- YAML 雙通道預設及八通道上限。
- 1、2、4、8 個 channel 狀態建立。
- 八個 Mock channel 同時 active。
- `max_concurrent_jobs=2` 時最大 active 數不超過 2。
- 單通道失敗隔離、recoverable retry、timeout、cancel。
- 非阻塞工作提交與 `job_id` 立即回覆。
- `erase`、`program`、`verify` 三階段進度及整體進度單調增加。
- `program`／`verify` 的 `bytes_done`、`bytes_total`。
- CLI 動態進度條包含 `ERASE`、`PROGRAM`、`VERIFY` 與 100%。
- CLI process 收到真正 `SIGINT` 後發出遠端 cancel，結果為 `cancelled`。
- retry backoff 期間取消會立即終止，不會誤啟動下一次 attempt。
- 等待全域 concurrency slot 時可立即取消，不必等其他通道完成。
- 取消後 `safe_shutdown()` 執行，且同一通道仍能完成下一個工作。
- `safe_shutdown()` 失敗時回報 `E5002`，不會產生假成功。
- Manager 關閉會取消執行中與排隊中工作。
- program、verify、read、分段輸出與 verify mismatch。
- `result.json`、Job JSONL、文字 log 與 Server recovery。
- TCP Client／Server program、status、cancel、protocol error 與斷線後存活。
- Queue full 回傳 `E4003`，Job log 寫入失敗回傳 `E8001` 且 worker 可繼續服務。
- OpenOCD／FPGA 未配置狀態回傳明確 `E5003`，不會假成功。
- Mock 越界操作在回報進度前拒絕；故障注入設定不會污染呼叫端。

額外執行：

```bash
./scripts/run_cli_e2e.sh
```

結果：`CLI E2E: status/progress/program/read passed`。

另執行：

```bash
./scripts/run_cli_cancel_e2e.py
```

結果：`CLI Ctrl+C E2E: remote cancel and channel recovery passed`。

另在臨時 venv 執行 editable install，確認 `plasma`、`plasma-server` console entry point 與 package lazy import 均可用。

本次使用 `run_trace_coverage.sh` 相容入口重新執行 pytest-cov，production modules
line coverage 為 83%（1795 statements，302 missing）。這是 line coverage，並非
branch coverage；不可與先前 Python trace 的近似百分比直接比較。

## 未驗證

- OpenOCD 實際 process command 與 STM32F103C8T6。
- PYNQ Linux 版本相容性。
- PYNQ-Z2 FPGA register map、AXI/GPIO/FIFO。
- 兩個實體 target 同時燒錄。
- 電源、reset、SWD、短路隔離及 100-cycle 壓力測試。
- Internet-facing security、TLS、authentication。

因此，本報告只能證明純軟體 Prototype 的行為符合目前測試規格，不能證明實體燒錄器已完成。
