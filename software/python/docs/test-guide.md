# Plasma v0.3.3 測試指南

本文件說明如何重跑純軟體測試、驗證 Client／Server、Protocol v3.3 one-based Site identity，以及未來如何執行硬體測試。

## 1. 測試環境

最低需求：Python 3.11+、PyYAML 6.0+。純軟體測試不需要 Z2、STM32 或 OpenOCD。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

判定基準是 exit code `0` 且沒有 failed/error；測試數量不是 contract。

## 2. 核心測試 contract

| 類別 | 主要驗證 |
|---|---|
| Protocol v3.3 | `PLASMA33`、`site_id >= 1`、round-trip、fragment、半包、版本、JSON、BINLEN、Image SHA-256 |
| Config | canonical `ppu/sites`、Site IDs 1..N、未知/退休欄位 fail closed |
| Programming Asset | Asset type/format validation、source SHA、`image+binary` normalization、unsupported normalizer rejection |
| Normalized Image | `image_size` / `image_sha256`、Program/Verify execution data integrity |
| SiteManager | 1/2/4/8 Sites、全域並行數、disabled/invalid、queue、cancel |
| Fault injection | program failure、retry、timeout、cancel、verify mismatch、safe shutdown failure |
| Progress | 非阻塞提交、獨立操作進度、整體進度、byte count |
| CLI | one-based `--site`、`SITE1` 顯示、`Ctrl+C` 遠端取消 |
| Isolation | SITE 1 failed 時 SITE 2 仍可 success |
| Output | `read_SITE<n>_...`、分段 read、檔名碰撞拒絕、`result.json`、JSONL 完整性 |
| REST v3 | Programming Asset routes/fields、strict unknown-field rejection、REST/wire boundary |
| Browser E2E | Engineering selection、batch、cancel、Asset cache/reconnect、observability |
| Full-stack acceptance | Browser/REST/Provider/Protocol/Server/Mock Interface 的真實 stack traversal |

Canonical 測試不得建立 `SITE 0`，也不得以退休的 Programmer/Channel/Firmware contract 當 current runtime expectation。

## 3. 手動 Client／Server smoke test

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

建立測試 Image：

```bash
python3 -c "from pathlib import Path; Path('/tmp/plasma-demo.bin').write_bytes(bytes(range(256)))"
```

執行：

```bash
plasma program --site 1 --bin /tmp/plasma-demo.bin --retries 1
plasma read --site 1 --map config/map.example.json
```

驗收條件：

- response 使用 `protocol_version: "3.3"`。
- wire magic 為 `PLASMA33`。
- canonical identity 是 `site_id: 1`。
- Program 只執行 write，不隱含 Erase/Verify。
- Program/Verify Image SHA 與實際 normalized Image 一致。
- `output/<job-id>/result.json` 存在。
- Read 產生 `read_SITE1_*.bin`。
- `logs/<date>/SITE1/` 使用 canonical Site identity。

## 4. REST v3 Programming Asset 測試

REST 接收 source/input model：

```text
Programming Asset
  asset_name
  asset_type
  asset_format
  asset_size
  asset_sha256
```

Program/Verify 前由 Gateway/Provider normalize 成 execution Image，再送入 Protocol v3.3。現在只有 `image + binary` normalizer 已實作；HEX/SREC/ELF/CSV/TXT 等宣告格式若沒有 parser 必須 fail closed。

Serial Number 是獨立 Asset type，不得被誤當成 Image 或 security key。

## 5. 進度與取消測試

```bash
plasma program --site 1 --bin /tmp/plasma-demo.bin --timeout 15
```

工作中按 `Ctrl+C`。必須同時成立：

- Server snapshot `cancel_requested=true`。
- terminal state 是 `cancelled`。
- `safe_shutdown()` 已被呼叫。
- SITE 1 之後仍能接受下一個工作。
- unrelated Site 不受影響。

## 6. 1/2/4/8 Site 並行測試

核心驗收不是只有 status entry 數量，而是 activity tracker 真的觀察到允許的 operation 同時 active。若 `max_concurrent_jobs=2`，即使存在八個 Sites，最大並行數仍不得超過 2。

Program/Verify 若共享同一 physical PPU resource，必須依 Normalized Image SHA 執行明確的 Image lease/arbitration；不同 Site 不得因為 batch orchestration 而無條件彼此等待。

## 7. Browser / Full-stack Acceptance

Web tests 包含 source/SSR 與 Playwright E2E。`Mock CD` 與 `Mock CD Browser Runtime Acceptance` 更進一步啟動真實 software stack，驗證 Browser → REST Gateway → Provider → Plasma Protocol v3.3 → Plasma Server → Mock Interface。

Acceptance PASS 仍不等於 hardware validation。

## 8. 測試失敗判讀

- `ModuleNotFoundError: yaml`：尚未安裝 dependencies。
- `Address already in use`：Server port 已被其他程序使用。
- `E4002 SITE_DISABLED`：該 Site 存在但已停用。
- `E3001 PROTOCOL_HEADER_INVALID`：檢查 `PLASMA33` 與 metadata version。
- checksum mismatch：檢查 normalized Image bytes 與 `image_sha256`。
- 測試卡住：不要用任意 sleep 猜 race；cancel/concurrency 測試使用 Event/barrier 做 deterministic synchronization。

## 9. 尚未執行的硬體 Acceptance

純軟體測試不能替代：

- Z2/FPGA loopback data integrity、1 KiB-1 / 1 KiB / 1 KiB+1 / large-image boundaries。
- 真實 Site isolation、throughput、cancel、reconnect。
- OpenOCD/STM32、SPI Flash、I2C EEPROM 等 real target programming。
- target voltage、power/reset safety、brownout/open/short fault behavior。
- 多 Site repeated-cycle success rate 與耗時分布。

硬體案例應作為獨立 Hardware Acceptance，不和快速純軟體 suite 混為同一層級。
