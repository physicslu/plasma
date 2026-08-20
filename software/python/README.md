# Plasma PPU control plane v0.3.2

Plasma 是可配置 **1～8 個 Programming Sites** 的 IC programming platform prototype。Python control plane 將一台實體設備建模為 **Plasma Programming Unit (PPU)**，每個 PPU 內含多個可獨立排程與執行工作的 **Site**。

```text
Facility
└── PPU
    ├── SITE 1
    ├── SITE 2
    └── ... SITE N
```

Canonical Site ID 從 **1** 開始，不存在 `SITE 0`。

目前純軟體/Mock path 有自動測試；OpenOCD、STM32F103C8T6 與 Z2/FPGA 的完整實機 programming validation 仍是獨立階段。

## Canonical contracts

### Domain

```text
PPUConfig
SiteConfig
SiteManager
SiteWorker
SiteState
site_id = 1..N
max_supported_sites
max_queue_depth_per_site
```

### Plasma Protocol v3.3

```text
Magic:            PLASMA33
protocol_version: 3.3
identity:         site_id = 1..N
execution data:   image_size / image_sha256 / normalized Image bytes
```

Protocol v3.3 是目前唯一 canonical runtime wire contract。

### Web REST v3

REST source/input model 使用 **Programming Asset**：

```text
Programming Asset
├── Image
├── Key
├── Option
├── Serial Number
└── Calibration
```

Declared formats：

```text
binary
intel_hex
srec
elf
csv
text
json
pem
```

只有 `Image + binary` normalizer 已實作。其他 Asset type/format 目前只是 extension point，執行時會 fail closed。

REST 的 Programming Asset 與 wire 的 Normalized Image 是不同 abstraction：

```text
Programming Asset
    |
    | parse / normalize
    v
Normalized Image
    |
    | Protocol v3.3
    v
PPU execution
```

Programming Recipe 是「PPU 要做什麼」的 control-plane concept，不屬於 Programming Asset。

`serial_number` 是 per-device identity Asset，不是 security key，也不應直接沿用 PPU-wide Image sharing semantics。

## 已完成的功能

- Python 3.11+。
- YAML 動態設定 1～8 個 one-based Sites，任一 Site 可停用。
- 每個 Site 有獨立 queue、worker、state、interface instance 與 audit log。
- 全域 `max_concurrent_jobs` 控制執行並行度。
- 操作：Erase / Program / Verify / Read / Status / Cancel。
- Program 只負責寫入 Image；完整流程由 Client/Web 明確組合，例如 `erase -> program -> verify`。
- Plasma v3.3 framed protocol：metadata/map/binary length + `PLASMA33` magic。
- Image SHA-256、payload size 與 incomplete-frame validation。
- 統一錯誤碼與 recoverable classification。
- Site errors：`SITE_INVALID` / `SITE_DISABLED` / `SITE_BUSY`。
- Job timeout / retry / backoff / cancel。
- CLI 單行 progress display 與安全取消。
- 單一 Site 失敗不會停止無關 Site。
- Server log、Job text log、JSONL audit log。
- `job_state.json` / `result.json` / read-back binary。
- Server startup recovery 將不完整 Job 標記為 `ABORTED`。
- Plasma Web REST Gateway 提供 status、Job、cancel、read-back download 與 Engineering Programming Asset routes。
- Engineering Mock Provider 支援 3 Facilities × 4 PPUs，Site 數 2/4/6/8。
- Engineering session/PPU 可 cache 多個 Programming Assets。
- Program/Verify 以 **Normalized Image SHA** 建立 PPU-wide active Image lease。
- Optional `plasma_manager` 提供手動 PPU registry 與 read-only fleet aggregation；Manager 不參與 PPU 本地 Job execution。
- `pytest` 是統一 Python test runner。

## Python 結構

```text
software/python/
├── config/
├── plasma_client/
├── plasma_core/
│   ├── assets.py             # Programming Asset + Normalized Image model
│   ├── models.py             # JobRequest / JobResult
│   └── protocol.py           # Protocol v3.3 / PLASMA33
├── plasma_handlers/
├── plasma_interfaces/
├── plasma_manager/           # optional read-only fleet control plane
├── plasma_server/
│   ├── site_manager.py
│   ├── site_worker.py
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

預設 code-level listener 為 `127.0.0.1:9900`。若允許遠端 Client，必須另外規劃 authentication、TLS 與 firewall；目前 prototype 不應把 raw TCP Server 直接暴露到 Internet。

## 啟動 Plasma Web REST Gateway

```bash
plasma-web --host 127.0.0.1 --port 8080 \
  --plasma-host 127.0.0.1 --plasma-port 9900
```

Core local routes 包含：

```text
GET  /api/status
POST /api/jobs
POST /api/jobs/{job_id}/cancel
GET  /api/jobs/{job_id}/files/{filename}
```

Engineering Programming 使用 REST v3 Programming Asset routes，詳見：

```text
docs/architecture/web-rest-api-contract.md
docs/architecture/engineering-programming-workspace.md
```

實際 deployment parameters 由 `scripts/plasmactl` 與 operator-local config 決定；不要把 code-level default 當成 deployment source of truth。

## Plasma Manager

Manager 是 optional read-only fleet control plane：

```bash
plasma-manager --config config/manager.example.yaml
```

目前提供：

```text
GET /api/health/live
GET /api/registry
GET /api/fleet
```

Manager 不提供 Job command routing、central scheduling、automatic discovery、authentication policy 或 Fleet Web UI。

## CLI

查詢 PPU / Sites：

```bash
plasma --host 127.0.0.1 --port 9900 status
```

Program raw binary Image 至 SITE 1：

```bash
plasma --host 127.0.0.1 --port 9900 program \
  --site 1 \
  --bin application.bin \
  --timeout 30 \
  --retries 1
```

其他操作：

```bash
plasma erase --site 1
plasma verify --site 1 --bin application.bin
plasma read --site 1 --map config/map.example.json
plasma status --site 1
```

CLI 的 `--bin` 表示目前 CLI 的 source input 是 raw binary Image；未來 HEX/ELF 等 parser 必須在明確實作後才可宣稱支援。

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

Configuration 使用 canonical `ppu/sites` vocabulary only。

## Output 與 audit log

每個 Job：

```text
output/<job-id>/
├── job_state.json
├── result.json
└── read_SITE1_<section>.bin
```

Canonical log path：

```text
logs/YYYY-MM-DD/
├── server.log
└── SITE1/
    ├── <job-id>.log
    └── <job-id>.jsonl
```

所有 audit timestamps 採帶時區 UTC ISO 8601；presentation layer 可轉成當地時間。

## 已知限制

- 尚無完整 authentication、TLS、authorization 或 anti-replay 機制。
- Job persistence 仍以檔案為主；高工作量需重新評估資料層。
- TCP 目前一個 request 對一個 connection，沒有長連線 multiplexing/server-push。
- 只有 raw binary Image Asset normalization 已實作。
- Programming Recipe/Package 尚未成為 executable contract。
- Server restart 可辨識未完成 Job，但不會自動重做 programming。
- Manager 目前只做 read-only aggregation 與 opt-in deployment。
- OpenOCD binary staging、adapter isolation 與實體 target 尚未完整驗證。
- FPGA register map、AXI/FIFO、SWD engine、power-good 與安全關電仍屬後續硬體整合。
