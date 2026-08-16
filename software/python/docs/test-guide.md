# Plasma v0.3.1 測試指南

本文件說明如何重跑純軟體測試、驗證 Client／Server，以及未來如何執行硬體測試。

## 1. 測試環境

最低需求：

- Python 3.11 以上。
- PyYAML 6.0 以上。
- 不需要 PYNQ-Z2、STM32 或 OpenOCD。

安裝：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## 2. 一鍵執行全部純軟體測試

```bash
./scripts/run_tests.sh
```

預期最後顯示：

```text
75 passed, 8 subtests passed in ...
```

若未來增加測試，數字可以大於 75；判定基準是 exit code `0` 且沒有 failed/error。

不使用 script：

```bash
python3 -m pytest -q
```

另可執行真實 Server process + CLI process 的端對端測試：

```bash
./scripts/run_cli_e2e.sh
```

預期顯示 `CLI E2E: status/progress/program/read passed`。

執行真正的 CLI process `Ctrl+C` 取消測試：

```bash
./scripts/run_cli_cancel_e2e.py
```

這個測試會啟動獨立 Server 與 CLI process，在 `program` 途中向 CLI 發送 `SIGINT`，確認遠端 Job 變成 `cancelled`，再提交一個新 `erase`，確認通道仍能服務。預期顯示：

```text
CLI Ctrl+C E2E: remote cancel and channel recovery passed
```

只跑單一測試檔：

```bash
python3 -m pytest -q tests/test_protocol.py
python3 -m pytest -q tests/test_channel_manager.py
python3 -m pytest -q tests/test_client_server.py
```

Coverage：

```bash
python3 -m pytest -q --cov=plasma_core --cov=plasma_server --cov-report=term-missing
```

相容入口（目前同樣委派給 pytest-cov）：

```bash
./scripts/run_trace_coverage.sh
```

歷史 trace 百分比不可與目前 pytest-cov 結果直接比較；新的 coverage 基準應以
pytest-cov 同一組參數重新產生。

## 3. 測試涵蓋範圍

| 類別 | 主要驗證 |
|---|---|
| Protocol | round-trip、fragment、半包、magic、版本、JSON、BINLEN、SHA-256 格式與內容 |
| Config | 預設雙通道、最多八通道、重複 ID、hex register base |
| Manager | 1/2/4/8 CH、全域並行數、disabled/invalid、重複 Job、等待名額時取消 |
| Fault injection | program failure、retry、timeout、cancel、verify mismatch、safe shutdown failure |
| Progress | 非阻塞提交、三階段進度、整體進度單調增加、byte count |
| CLI | 動態進度條、`Ctrl+C` 遠端取消、取消後通道恢復 |
| Isolation | CH0 failed 時 CH1 success |
| Output | 分段 read、獨立檔名、檔名碰撞拒絕、`job_id` 路徑安全、`result.json`、JSONL 完整性 |
| Recovery | 重啟後把不完整 Job 標為 `ABORTED` |
| Network | status、program、checksum、版本、型別驗證、斷線、第二連線 cancel |
| Interface boundary | Mock 正常流程／設定隔離／越界預檢、OpenOCD/FPGA 未配置時的明確錯誤 |

## 4. 手動 Client／Server 測試

終端 A：

```bash
source .venv/bin/activate
plasma-server --config config/plasma.yaml
```

終端 B：

```bash
source .venv/bin/activate
plasma status
```

建立測試 binary：

```bash
python3 -c "from pathlib import Path; Path('/tmp/plasma-demo.bin').write_bytes(bytes(range(256)))"
```

執行燒錄與讀回：

```bash
plasma program --channel 0 --bin /tmp/plasma-demo.bin --retries 1
plasma read --channel 0 --map config/map.example.json
```

檢查：

```bash
find output -maxdepth 2 -type f -print
find logs -maxdepth 4 -type f -print
```

驗收條件：

- program response 的 `result.state` 為 `success`。
- `output/<job-id>/result.json` 存在。
- read Job 產生兩個不互相覆蓋的 `.bin`。
- `logs/<date>/CH0/` 同時存在 `.log` 與 `.jsonl`。
- CLI 依序出現 `ERASE`、`PROGRAM`、`VERIFY`，最後為 `100.0%`。

## 5. 進度與取消測試

預設 Mock program 約需 6 秒，可直接觀察：

```bash
plasma program --channel 0 --bin /tmp/plasma-demo.bin --timeout 15
```

在任一階段按 `Ctrl+C`。預期 CLI 顯示取消要求，最後 stdout JSON 包含：

```json
{
  "result": {
    "state": "cancelled"
  }
}
```

也可保留原 CLI，從另一個終端先查詢 Job ID，再取消：

```bash
plasma status --job <job-id>
plasma cancel --job <job-id>
```

驗收條件不是「CLI 關掉」而已，必須同時成立：

- Server snapshot 的 `cancel_requested=true`。
- terminal state 是 `cancelled`。
- error code 是 `E7002 OPERATION_CANCELLED`。
- `safe_shutdown()` 已被呼叫。
- 同一通道之後能成功接受下一個工作。

## 6. 故障注入測試

複製設定檔，在 CH0 加入：

```yaml
mock:
  failures:
    program: 1
  failure_recoverable: true
```

然後使用 `--retries 1`。預期第一次 program 失敗，整個 Job 重新執行，第二次成功；JSONL 應包含 `job_retry`。

若將 `failure_recoverable` 改為 `false`，預期不重試，result 為 `failed` 並包含 `E6002`。

Timeout：

```yaml
mock:
  delays:
    erase: 1.0
```

```bash
plasma erase --channel 0 --timeout 0.1
```

預期 result state 是 `timeout`，error code 是 `E7001`。

## 7. 八通道軟體測試

自動測試已建立八個 Mock channel 並同時提交不同 firmware。核心驗收不是只有八個 status entry，而是 activity tracker 曾觀察到八個 operation 同時 active。

另有一個測試把 `max_concurrent_jobs` 設為 2，再提交八個工作；觀察到的最大並行數必須恰好為 2。

## 8. 測試失敗判讀

- `ModuleNotFoundError: yaml`：尚未執行 `pip install -e .`。
- `Address already in use`：9900 port 已被其他程序使用；修改 YAML port。
- `E4002 CHANNEL_DISABLED`：該通道在 YAML 中是 `enabled: false`。
- `E3006 PROTOCOL_CHECKSUM_MISMATCH`：傳輸 binary 與 metadata hash 不同。
- `E8001 OUTPUT_WRITE_FAILED`：檢查 output/log 目錄權限與磁碟空間。
- 測試卡住：先確認沒有把 Mock delay 設成很大；硬體測試不得混入純軟體 test suite。

## 9. 尚未執行的硬體測試

以下項目不能由純軟體測試替代：

- OpenOCD 能否辨識實際 adapter 與 STM32F103C8T6。
- CH0、CH1 是否使用真正獨立的 adapter、port、reset 與 power。
- 燒錄時的 SWD 波形、target voltage、突入電流與 power-good。
- 拔除 target、SWDIO/SWCLK 開路、短路與 brownout。
- 兩通道各連續 100 次燒錄的成功率與耗時分布。
- FPGA register map、AXI timeout、interrupt 與 safe power-off。

硬體完成後應將這些案例標記為 hardware tests，與快速純軟體測試分開執行。
