# Plasma PPU control plane v0.3.2

Plasma 是一個可配置 **1～8 個 Programming Sites** 的 IC 燒錄平台 Prototype。Python control plane 將一台實體燒錄設備建模為 **Plasma Programming Unit (PPU)**，每個 PPU 內含多個可獨立排程與執行工作的 **Site**。

Canonical domain hierarchy：

```text
Facility
└── PPU
    ├── SITE 1
    ├── SITE 2
    └── ... SITE N
```

> Canonical Site ID 從 **1** 開始，不存在 `SITE 0`。本版本已完成純軟體自動測試，但尚未完成 OpenOCD、STM32F103C8T6 與 Z2／FPGA 的完整實機燒錄驗證。`OpenOCDInterface` 與 `FPGAInterface` 是整合邊界，不代表硬體功能已完成。

## Domain naming 與 Protocol v3.2

Python / REST / CLI / Web / TCP wire 的 canonical vocabulary 已統一為 `PPU`、`Facility`、`Site`：

- `PPUConfig`
- `SiteConfig`
- `SiteManager`
- `SiteWorker`
- `SiteState`
- `site_id = 1..N`
- `max_supported_sites`
- `max_queue_depth_per_site`
- CLI `--site`

Plasma TCP protocol canonical version 是 **v3.2**：

```text
Magic:            PLASMA32
protocol_version: 3.2
identity:         site_id = 1..N
```

Server 暫時保留 v3.1 compatibility adapter：

```text
v3.1 channel_id 0 -> canonical SITE 1
v3.1 channel_id 1 -> canonical SITE 2
...
```

v3.1 使用 `PLASMA31`、zero-based `channel_id` 與 legacy `programmer/channels` response shape；v3.2 不再混入這些欄位。Python distribution name `plasma-multichannel` 暫時保留，避免安裝 identity 在這次 protocol migration 中無意改變。

## 已完成的功能

- Python 3.11+。
- YAML 動態設定 1～8 個 one-based Sites，任一 Site 可個別停用。
- 每個 Site 有獨立 queue、worker、state、interface instance 與 audit log。
- 全域 `max_concurrent_jobs` 限制，避免硬體資源過載。
- 操作：`erase`、`program`、`verify`、`read`、`status`、`cancel`。
- `program` 只負責寫入 Firmware；完整流程由 Client／Web UI 決定是否依序送出 `erase → program → verify`。
- Plasma v3.2 framed protocol：明確 metadata、map、binary 長度與 `PLASMA32` magic。
- v3.1 `PLASMA31/channel_id` compatibility decoding。
- Binary SHA-256 驗證、封包大小上限與不完整資料偵測。
- 統一錯誤碼、recoverable 分類與原始例外保留。
- v3.2 Site errors：`SITE_INVALID`、`SITE_DISABLED`、`SITE_BUSY`；E4001/E4002/E4003 數值不變。
- 每個 Job 支援 timeout、retry、backoff、cancel。
- CLI 單行動態進度顯示與安全取消。
- 單一 Site 失敗不會停止其他 Site。
- Server log、Job text log、JSONL audit log。
- `job_state.json`、`result.json` 與 read-back binary。
- 原子寫檔；Server 啟動時會把先前未完成的工作標記為 `ABORTED`。
- Plasma Web REST Gateway 提供狀態、工作提交、取消與 read-back 下載。
- `pytest` 是統一 Python test runner。

## Python 結構

```text
software/python/
├── config/
│   └── plasma.yaml
├── plasma_client/
├── plasma_core/
├── plasma_handlers/
├── plasma_interfaces/
├── plasma_server/
│   ├── site_manager.py      # canonical one-based domain
│   ├── site_worker.py       # canonical one-based execution
│   ├── channel_manager.py   # v3.1 compatibility facade
│   ├── channel_worker.py    # legacy import compatibility
│   └── server.py
├── plasma_web/
├── tests/
└── pyproject.toml
```

## 安裝與測試

```bash
cd software/python
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

## 啟動 Plasma Server

```bash
source .venv/bin/activate
plasma-server --config config/plasma.yaml
```

或：

```bash
python3 -m plasma_server.server --config config/plasma.yaml
```

預設監聽 `127.0.0.1:9900`。若允許遠端 Client，必須另外規劃 authentication、TLS 與 firewall；目前 Prototype 尚未提供完整網路安全層，不應把 raw TCP Server 直接暴露到 Internet。

## 啟動 Plasma Web REST Gateway

先啟動 Plasma Server，再啟動 Gateway：

```bash
plasma-web --host 127.0.0.1 --port 8080 \
  --plasma-host 127.0.0.1 --plasma-port 9900
```

Gateway 提供 `GET /api/status`、`POST /api/jobs`、`POST /api/jobs/{job_id}/cancel` 與 read-back file download。Canonical REST request 使用 one-based `site_id`，Gateway 以 v3.2 與 Server 溝通。舊 `channel/channel_id` 只在 REST compatibility boundary 被視為 zero-based legacy identity 並轉成 Site。

> 實際部署參數由 repository `scripts/plasmactl` 與本機 deployment config 決定；不要把上述 code-level default 當成部署端口的 source of truth。

## CLI

查詢 PPU / 所有 Sites：

```bash
plasma --host 127.0.0.1 --port 9900 status
```

只寫入 Firmware 至 SITE 1：

```bash
plasma --host 127.0.0.1 --port 9900 program \
  --site 1 \
  --bin firmware.bin \
  --timeout 30 \
  --retries 1
```

CLI 進度使用 one-based Site vocabulary：

```text
Job job-... queued. Press Ctrl+C to cancel.
SITE1 PROGRAM   [████████████████────────────]  58.9%  stage 58.9%  38,600/65,536 B
SITE1 PROGRAM   [████████████████████████████] 100.0%  stage 100.0% 65,536/65,536 B
```

其他操作：

```bash
plasma erase --site 1
plasma verify --site 1 --bin firmware.bin
plasma read --site 1 --map config/map.example.json
plasma status --site 1
```

新版 CLI 不再把 `--channel` 當作 public interface；若必須驗證 v3.1 wire compatibility，使用明確設定為 protocol 3.1 的 Client adapter，不要在新操作流程中混用兩套 ID。

## Canonical YAML

```yaml
ppu:
  id: ppu-01
  facility_id: lab-01
  model: PYNQ-Z2
  display_name: Plasma PPU Prototype

server:
  host: 127.0.0.1
  port: 9900
  max_supported_sites: 8
  max_concurrent_jobs: 2
  max_queue_depth_per_site: 16

sites:
  - {id: 1, enabled: true, interface: mock}
  - {id: 2, enabled: true, interface: mock}
  - {id: 3, enabled: false, interface: mock}
```

`max_supported_sites` 定義 Site ID 空間 `1..N`；`max_concurrent_jobs` 定義同時真正執行的 Job 數。兩者不是同一件事。

舊 YAML 的 `programmer`、`channels`、`max_supported_channels` 等名稱仍可讀取。若使用 legacy `channels:`，其 ID 被視為 v3.1 zero-based Channel ID，在 config loader 邊界轉成 one-based Site ID；進入 canonical domain 後不再存在 Site 0。

## Output 與 audit log

每個 Job 使用獨立 output 目錄：

```text
output/<job-id>/
├── job_state.json
├── result.json
├── read_SITE1_section0.bin
└── read_SITE1_section1.bin
```

Canonical log path：

```text
logs/YYYY-MM-DD/
├── server.log
└── SITE1/
    ├── <job-id>.log
    └── <job-id>.jsonl
```

Canonical `SITE1/*.jsonl` 只寫 `site_id: 1`。Migration 期間另有小型 legacy mirror `CH0/`，其 JSONL 只寫 `channel_id: 0`；兩套 schema 不在同一 log record 中混用。Read-back binary 不重複建立 legacy `read_CH*` 副本。

所有時間採帶時區的 UTC ISO 8601；UI 若要顯示當地時間，應在 presentation layer 轉換，不應改寫 audit timestamp。

## Mock 故障注入

測試用 Site 可在 YAML 注入延遲與失敗：

```yaml
mock:
  default_delay_s: 0.01
  delays:
    program: 0.2
  failures:
    program: 1
  failure_recoverable: true
```

這是 test facility，不應帶入 production configuration。

## 已知限制

- 尚無完整 authentication、TLS、authorization 或 anti-replay 機制。
- Job persistence 目前仍以檔案為主；高工作量需重新評估資料層。
- TCP 仍採一個 request 對一個 connection，沒有長連線多工或 server-push event stream。
- v3.1 compatibility adapter 暫時保留；移除時必須另做 deprecation/removal decision。
- Server 重啟可辨識未完成工作，但不會自動重做燒錄。
- OpenOCD binary staging、adapter isolation、port 配置與實體 target 尚未完成完整驗證。
- FPGA register map、AXI/FIFO、SWD engine、power-good 與安全關電仍屬後續硬體整合工作。
