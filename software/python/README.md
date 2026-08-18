# Plasma PPU control plane v0.3.1

Plasma 是一個可配置 **1～8 個 Programming Sites** 的 IC 燒錄平台 Prototype。Python control plane 將一台實體燒錄設備建模為 **Plasma Programming Unit (PPU)**，每個 PPU 內含多個可獨立排程與執行工作的 **Site**。

Canonical domain hierarchy：

```text
Facility
└── PPU
    ├── SITE 0
    ├── SITE 1
    └── ...
```

> 本版本已完成純軟體自動測試，但尚未完成 OpenOCD、STM32F103C8T6 與 Z2／FPGA 的完整實機燒錄驗證。`OpenOCDInterface` 與 `FPGAInterface` 是整合邊界，不代表硬體功能已完成。

## Domain naming 與 v3.1 compatibility

Python / REST / CLI 的 canonical vocabulary 已統一為 `PPU`、`Facility`、`Site`：

- `PPUConfig`
- `SiteConfig`
- `SiteManager`
- `SiteWorker`
- `SiteState`
- `site_id`
- `max_supported_sites`
- `max_queue_depth_per_site`
- CLI `--site`

Plasma TCP protocol **仍是 v3.1**。v3.1 frame 的既有 wire key `channel_id` 暫時保留；這是 protocol compatibility boundary，不代表 Channel 仍是 Python domain 主詞。舊的 `ChannelConfig`、`ChannelManager`、`ChannelWorker`、`ChannelState`、`--channel` 等名稱只作 migration alias。

同理，Python distribution name `plasma-multichannel` 暫時保留以避免安裝 identity 無意中改變；產品與 domain naming 已改為 PPU / Site。

## 已完成的功能

- Python 3.11+。
- YAML 動態設定 1～8 個 Sites，任一 Site 可個別停用。
- 每個 Site 有獨立 queue、worker、state、interface instance 與 audit log。
- 全域 `max_concurrent_jobs` 限制，避免硬體資源過載。
- 操作：`erase`、`program`、`verify`、`read`、`status`、`cancel`。
- `program` 只負責寫入 Firmware；完整流程由 Client／Web UI 決定是否依序送出 `erase → program → verify`。
- Plasma v3.1 framed protocol：明確 metadata、map、binary 長度。
- Binary SHA-256 驗證、封包大小上限與不完整資料偵測。
- 統一錯誤碼、recoverable 分類與原始例外保留。
- 每個 Job 支援 timeout、retry、backoff、cancel。
- CLI 單行動態進度顯示與安全取消。
- 單一 Site 失敗不會停止其他 Site。
- Server log、Job text log、JSONL audit log。
- `job_state.json`、`result.json` 與 read-back binary。
- 原子寫檔；Server 啟動時會把先前未完成的工作標記為 `ABORTED`。
- Browser REST Gateway 提供狀態、工作提交、取消與 read-back 下載。
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
│   ├── site_manager.py      # canonical
│   ├── site_worker.py       # canonical
│   ├── channel_manager.py   # compatibility shim
│   ├── channel_worker.py    # compatibility shim
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

正式 runtime 目前只有設定檔解析需要 `PyYAML`；pytest/coverage 位於 `dev` extra。

## 啟動 Plasma Server

```bash
source .venv/bin/activate
plasma-server --config config/plasma.yaml
```

或：

```bash
python3 -m plasma_server.server --config config/plasma.yaml
```

預設監聽 `127.0.0.1:9900`。若允許遠端 Client，必須另外規劃 authentication、TLS 與 firewall；目前 v0.3.1 尚未提供完整網路安全層，不應把 raw TCP Server 直接暴露到 Internet。

## 啟動 Plasma Web REST Gateway

先啟動 Plasma Server，再啟動 Gateway：

```bash
plasma-web --host 127.0.0.1 --port 8080 \
  --plasma-host 127.0.0.1 --plasma-port 9900
```

Gateway 提供 `GET /api/status`、`POST /api/jobs`、`POST /api/jobs/{job_id}/cancel` 與 read-back file download。REST request 使用 canonical `site_id`; Gateway 在內部把 Site ID 轉成 v3.1 TCP `channel_id`。

> SWPC 的實際部署參數由 repository `scripts/plasmactl` 與本機 deployment config 決定；不要把上述 code-level default 當成部署端口的 source of truth。

## CLI

查詢 PPU / 所有 Sites：

```bash
plasma --host 127.0.0.1 --port 9900 status
```

只寫入 Firmware 至 SITE 0：

```bash
plasma --host 127.0.0.1 --port 9900 program \
  --site 0 \
  --bin firmware.bin \
  --timeout 30 \
  --retries 1
```

CLI 進度使用 Site vocabulary：

```text
Job job-... queued. Press Ctrl+C to cancel.
SITE0 PROGRAM   [████████████████────────────]  58.9%  stage 58.9%  38,600/65,536 B
SITE0 PROGRAM   [████████████████████████████] 100.0%  stage 100.0% 65,536/65,536 B
```

其他操作：

```bash
plasma erase --site 0
plasma verify --site 0 --bin firmware.bin
plasma read --site 0 --map config/map.example.json
plasma status --site 0
```

Migration 期間舊參數仍可用：

```bash
plasma erase --channel 0
```

但新文件與新程式不得再把 `--channel` 當 canonical interface。

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
  - {id: 0, enabled: true, interface: mock}
  - {id: 1, enabled: true, interface: mock}
  - {id: 2, enabled: false, interface: mock}
```

`max_supported_sites` 定義 Site ID 空間；`max_concurrent_jobs` 定義同時真正執行的 Job 數。兩者不是同一件事。八個 Sites 可以存在，但因 CPU、USB、FPGA bus 或 power budget 只允許較少工作同時執行。

舊 YAML 的 `programmer`、`channels`、`max_supported_channels` 等名稱仍可讀取，但只作 migration compatibility。

## Output 與 audit log

每個 Job 使用獨立 output 目錄：

```text
output/<job-id>/
├── job_state.json
├── result.json
├── read_SITE0_section0.bin
└── read_SITE0_section1.bin
```

Canonical log path：

```text
logs/YYYY-MM-DD/
├── server.log
└── SITE0/
    ├── <job-id>.log
    └── <job-id>.jsonl
```

Migration 期間 Job log 會暫時 mirror 到舊 `CH<n>` 目錄，JSONL 也暫時同時包含 `site_id` 與 `channel_id`。新工具應只依賴 `SITE<n>` / `site_id`。

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
- TCP v3.1 仍採一個 request 對一個 connection，沒有長連線多工或 server-push event stream。
- v3.1 wire field 仍是 `channel_id`；未來若要改成 `site_id`，必須透過明確 protocol-version migration，不得靠 rename 偷改。
- Server 重啟可辨識未完成工作，但不會自動重做燒錄。
- OpenOCD binary staging、adapter isolation、port 配置與實體 target 尚未完成完整驗證。
- FPGA register map、AXI/FIFO、SWD engine、power-good 與安全關電仍屬後續硬體整合工作。
