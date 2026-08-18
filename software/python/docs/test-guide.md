# Plasma v0.3.2 測試指南

本文件說明如何重跑純軟體測試、驗證 Client／Server、Protocol v3.2 one-based Site identity，以及未來如何執行硬體測試。

## 1. 測試環境

最低需求：

- Python 3.11 以上。
- PyYAML 6.0 以上。
- 純軟體測試不需要 Z2、STM32 或 OpenOCD。

安裝：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## 2. 執行純軟體測試

```bash
./scripts/run_tests.sh
```

或：

```bash
python3 -m pytest -q
```

判定基準是 exit code `0` 且沒有 failed/error；測試數量會隨功能增加，不應把固定數字當 contract。

可另外執行真實 Server process + CLI process 的端對端測試：

```bash
./scripts/run_cli_e2e.sh
./scripts/run_cli_cancel_e2e.py
```

Coverage：

```bash
python3 -m pytest -q --cov=plasma_core --cov=plasma_server --cov-report=term-missing
```

## 3. 核心測試 contract

| 類別 | 主要驗證 |
|---|---|
| Protocol v3.2 | `PLASMA32`、`site_id >= 1`、round-trip、fragment、半包、版本、JSON、BINLEN、SHA-256 |
| v3.1 compatibility | `PLASMA31`、`channel_id 0 -> SITE 1`、response version mirror、legacy error names |
| Config | canonical `sites:` 為 1..N；legacy `channels:` zero-based 只在 loader 邊界轉換 |
| SiteManager | 1/2/4/8 Sites、全域並行數、disabled/invalid、queue、cancel |
| Fault injection | program failure、retry、timeout、cancel、verify mismatch、safe shutdown failure |
| Progress | 非阻塞提交、獨立操作進度、整體進度單調增加、byte count |
| CLI | one-based `--site`、`SITE1` 顯示、`Ctrl+C` 遠端取消 |
| Isolation | SITE 1 failed 時 SITE 2 仍可 success |
| Output | `read_SITE<n>_...`、分段 read、檔名碰撞拒絕、`result.json`、JSONL 完整性 |
| Audit | canonical `SITE1/site_id=1` 與 legacy mirror `CH0/channel_id=0` 分離 |
| Network | v3.2 status/program/cancel、checksum、型別驗證、斷線，以及 v3.1 compatibility |
| Interface boundary | FPGA `site_id=1`、legacy `channel_id=0 -> site_id=1`、OpenOCD/FPGA 未配置錯誤 |

Canonical 測試不得建立 `SITE 0`。只有明確標示 v3.1／Channel compatibility 的案例可以使用 `channel_id=0`。

## 4. 手動 Client／Server smoke test

終端 A：

```bash
source .venv/bin/activate
plasma-server --config config/plasma.yaml
```

終端 B：

```bash
source .venv/bin/activate
plasma status
plasma status --site 1
```

建立測試 binary：

```bash
python3 -c "from pathlib import Path; Path('/tmp/plasma-demo.bin').write_bytes(bytes(range(256)))"
```

執行燒錄與讀回：

```bash
plasma program --site 1 --bin /tmp/plasma-demo.bin --retries 1
plasma read --site 1 --map config/map.example.json
```

驗收條件：

- response 使用 `protocol_version: "3.2"`。
- canonical identity 是 `site_id: 1`，不得出現 `site_id: 0`。
- program response 的 `result.state` 為 `success`。
- `output/<job-id>/result.json` 存在。
- Read 產生 `read_SITE1_*.bin`。
- `logs/<date>/SITE1/` 存在 `.log` 與 `.jsonl`，canonical JSONL 只有 `site_id: 1`。
- Migration 期間 `logs/<date>/CH0/` 可存在 legacy mirror，其 JSONL 使用 `channel_id: 0`。
- CLI 的 program 工作只出現 `PROGRAM`，不會自動出現 `ERASE` 或 `VERIFY`。

## 5. 進度與取消測試

```bash
plasma program --site 1 --bin /tmp/plasma-demo.bin --timeout 15
```

工作中按 `Ctrl+C`。驗收不是「CLI 關掉」而已，必須同時成立：

- Server snapshot 的 `cancel_requested=true`。
- terminal state 是 `cancelled`。
- error code 是 `E7002 OPERATION_CANCELLED`。
- `safe_shutdown()` 已被呼叫。
- SITE 1 之後仍能接受下一個工作。

也可從另一個終端取消：

```bash
plasma status --job <job-id>
plasma cancel --job <job-id>
```

## 6. 故障注入

在 canonical SITE 1 加入：

```yaml
sites:
  - id: 1
    enabled: true
    interface: mock
    mock:
      failures:
        program: 1
      failure_recoverable: true
```

使用 `--retries 1`，預期第一次 program 失敗後依 policy 重試，JSONL 包含 `job_retry`。若 `failure_recoverable: false`，則不重試。

Timeout 範例：

```yaml
mock:
  delays:
    erase: 1.0
```

```bash
plasma erase --site 1 --timeout 0.1
```

預期 result state 是 `timeout`，error code 是 `E7001`。

## 7. 1/2/4/8 Site 並行測試

自動測試會建立不同 Site 數量並平行提交工作。核心驗收不是只有 status entry 數量，而是 activity tracker 真的觀察到允許的 operation 同時 active。

若 `max_concurrent_jobs=2`，即使存在八個 Sites，觀察到的最大並行數仍必須不超過 2。

## 8. v3.1 compatibility 測試

Compatibility 測試必須明確使用 v3.1 Client／Frame：

```text
PLASMA31
protocol_version = 3.1
channel_id = 0
```

Server 應將其導向 canonical SITE 1，並以 v3.1 shape 回覆 `channel_id=0`。v3.2 request 若帶 `channel_id` 應拒絕；v3.1 request 若偷帶 `site_id` 也應拒絕。

對 E4001/E4002/E4003：

```text
v3.2: SITE_INVALID / SITE_DISABLED / SITE_BUSY
v3.1: CHANNEL_INVALID / CHANNEL_DISABLED / CHANNEL_BUSY
```

## 9. 測試失敗判讀

- `ModuleNotFoundError: yaml`：尚未安裝 Python package/dev dependencies。
- `Address already in use`：Server port 已被其他程序使用。
- `E4002 SITE_DISABLED`：該 Site 存在但已停用。
- `E3001 PROTOCOL_HEADER_INVALID`：檢查 `PLASMA31/32` 與 metadata version 是否一致。
- `E3006 PROTOCOL_CHECKSUM_MISMATCH`：傳輸 binary 與 metadata hash 不同。
- `E8001 OUTPUT_WRITE_FAILED`：檢查 output/log 目錄權限與磁碟空間。
- 測試卡住：不要用任意 sleep 猜 race；cancel/concurrency 測試應使用 Event/barrier 做 deterministic synchronization。

## 10. 尚未執行的硬體測試

以下不能由純軟體測試替代：

- OpenOCD 能否辨識實際 adapter 與 STM32F103C8T6。
- SITE 1、SITE 2 是否使用真正獨立的 adapter、port、reset 與 power。
- 燒錄時 SWD 波形、target voltage、突入電流與 power-good。
- 拔除 target、SWDIO/SWCLK 開路、短路與 brownout。
- 多 Site 各連續 100 次燒錄的成功率與耗時分布。
- FPGA register map、AXI timeout、interrupt 與 safe power-off。

硬體完成後應將這些案例標記為 hardware tests，與快速純軟體 test suite 分開執行。
