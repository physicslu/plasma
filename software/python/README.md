# Plasma Multi-channel v0.3.1

Plasma 是一個多通道 IC 燒錄器的純 Python 控制層 Prototype。本版本的軟體架構可設定 **1～8 通道**，預設啟用 CH0、CH1，並以 `MockInterface` 驗證排程、通訊、錯誤隔離、timeout、retry、cancel、輸出與稽核紀錄。

> 本版本已完成純軟體自動測試，但尚未完成 OpenOCD、STM32F103C8T6 與 PYNQ-Z2／FPGA 實機驗證。`OpenOCDInterface` 與 `FPGAInterface` 是明確的整合邊界，不代表硬體功能已完成。

## 已完成的功能

- Python 3.11+。
- YAML 動態設定 CH0～CH7，任意通道可個別停用。
- 每通道獨立 queue、worker、state、interface instance 與 log。
- 全域 `max_concurrent_jobs` 限制，避免硬體資源過載。
- 操作：`erase`、`program`、`verify`、`read`、`status`、`cancel`。
- `program` 工作流程：`erase → program → verify`。
- v3.1 framed protocol：明確 metadata、map、binary 長度。
- Binary SHA-256 驗證、封包大小上限與不完整資料偵測。
- 統一錯誤碼、recoverable 分類及原始例外保留。
- 每個 Job 的 timeout、retry、backoff 與 cancel。
- `erase → program → verify` 可設定模擬時間並持續回報階段及整體進度。
- CLI 單行動態進度條，包含階段百分比與 program／verify 位元組數。
- CLI 執行期間按 `Ctrl+C` 會向 Server 送出取消要求並等待安全收尾。
- 也可從另一個終端以 `plasma cancel --job ...` 取消工作。
- CH0 失敗不會停止 CH1；其他通道亦同。
- Server log、Job 文字 log、JSONL 事件 log。
- `job_state.json`、`result.json` 與 read-back binary。
- 原子寫檔，避免未完成檔案直接成為正式輸出。
- Server 啟動時將先前未完成的工作標記為 `ABORTED`。
- Python 內建 `unittest` 測試，不強制依賴 pytest。
- 瀏覽器 REST Gateway：狀態查詢、Firmware 上傳、擦除、燒錄、驗證與取消。
- `job_id`、協定保留欄位、數值型別與 read-back 檔名的防禦性驗證。
- 等待全域執行名額的 Job 可立即取消；Server 關閉時取消執行中與排隊中工作。
- `safe_shutdown()` 失敗會回報 `E5002`，不再把未確認安全狀態的操作標示為成功。
- Mock 設定採獨立副本並拒絕未知／無效選項，避免故障注入污染原始設定。

## 專案結構

```text
plasma-multichannel-v0.3.1/
├── config/
│   ├── plasma.yaml
│   └── map.example.json
├── plasma_client/
├── plasma_core/
├── plasma_handlers/
├── plasma_interfaces/
├── plasma_server/
├── plasma_web/
├── tests/
├── docs/
├── scripts/
├── TEST_REPORT.md
└── pyproject.toml
```

## 安裝

### Web Gateway

先啟動既有 Plasma Server，再啟動瀏覽器 Gateway：

```bash
plasma-server --config config/plasma.yaml
plasma-web --host 0.0.0.0 --port 8080 --plasma-host 127.0.0.1 --plasma-port 9900
```

Gateway 提供 `GET /api/status`、`POST /api/jobs` 與
`POST /api/jobs/{job_id}/cancel`。`program`／`verify` 的 Firmware 由 Web UI
轉成 Base64 JSON 傳入；Job 仍由 Plasma Server 持有，關閉瀏覽器不等於取消工作。

```bash
cd plasma-multichannel-v0.3.1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

只有設定檔解析需要 `PyYAML`。開發者若要使用 pytest 與 coverage：

```bash
python -m pip install -e '.[dev]'
```

## 快速測試

不需安裝 pytest：

```bash
./scripts/run_tests.sh
```

或直接執行：

```bash
python3 -m unittest discover -s tests -v
```

不安裝第三方 coverage 套件也可產生 Python 內建 trace 摘要：

```bash
./scripts/run_trace_coverage.sh
```

詳細案例與判讀方式請看 [`docs/test-guide.md`](docs/test-guide.md)。本次實際結果在 [`TEST_REPORT.md`](TEST_REPORT.md)。

## 啟動 Server

```bash
source .venv/bin/activate
plasma-server --config config/plasma.yaml
```

未安裝 console script 時也可以：

```bash
python3 -m plasma_server.server --config config/plasma.yaml
```

預設監聽 `127.0.0.1:9900`。若要允許遠端 Client，必須明確把 `host` 改成 Server 的內網位址或 `0.0.0.0`，並另外規劃認證、TLS 與 firewall；v0.3.1 尚未提供網路安全層，不應直接暴露到 Internet。

## CLI 操作

查詢所有通道：

```bash
plasma --host 127.0.0.1 --port 9900 status
```

燒錄 CH0：

```bash
plasma --host 127.0.0.1 --port 9900 program \
  --channel 0 \
  --bin firmware.bin \
  --map config/map.example.json \
  --timeout 30 \
  --retries 1
```

執行時，進度寫到 stderr，最終 JSON 寫到 stdout，因此仍可把結果導向檔案：

```text
Job job-... queued. Press Ctrl+C to cancel.
CH0 ERASE     [██████──────────────────────]  21.1%  stage 63.3%
CH0 PROGRAM   [████████████████────────────]  58.9%  stage 76.7%  50,266/65,536 B
CH0 VERIFY    [██████████████████████████──]  94.4%  stage 83.3%  54,613/65,536 B
CH0 VERIFY    [████████████████████████████] 100.0%  stage 100.0% 65,536/65,536 B
```

若不需要進度條：

```bash
plasma program --channel 0 --bin firmware.bin --no-progress
```

擦除、驗證與讀回：

```bash
plasma erase --channel 0
plasma verify --channel 0 --bin firmware.bin
plasma read --channel 0 --map config/map.example.json
```

查詢單一 Job：

```bash
plasma status --job job-20260808-123456-abcdef12
```

從另一個終端取消執行中的 Job：

```bash
plasma cancel --job job-20260808-123456-abcdef12
```

也可以在正在顯示進度的 CLI 直接按 `Ctrl+C`。CLI 會先送出遠端取消要求，等待 Server 將 Job 標記為 `cancelled`，再輸出最終 JSON。這不是只關閉本機畫面。

## 通道設定

預設列出八個通道，只啟用前兩個：

```yaml
server:
  max_supported_channels: 8
  max_concurrent_jobs: 2

channels:
  - {id: 0, enabled: true, interface: mock}
  - {id: 1, enabled: true, interface: mock}
  - {id: 2, enabled: false, interface: mock}
  # CH3～CH7 省略
```

`max_supported_channels` 是可用的 channel ID 上限；`max_concurrent_jobs` 是同時真正執行的工作數。兩者不是同一件事。八個通道可以存在，但因 CPU、USB、FPGA bus 或電源限制只允許兩個同時工作。

## 輸出與紀錄

每個 Job 使用獨立目錄：

```text
output/<job-id>/
├── job_state.json
├── result.json
├── read_CH0_section0.bin
└── read_CH0_section1.bin
```

紀錄檔：

```text
logs/YYYY-MM-DD/
├── server.log
└── CH0/
    ├── <job-id>.log
    └── <job-id>.jsonl
```

所有時間採帶時區的 UTC ISO 8601。若上位機要顯示台灣時間，應在 UI 層轉成 `Asia/Taipei`，不要改寫原始稽核時間。

## Mock 故障注入

測試用通道可在 YAML 注入延遲與失敗：

```yaml
mock:
  default_delay_s: 0.01
  delays:
    program: 0.2
  failures:
    program: 1
  failure_recoverable: true
```

上例表示第一次 `program` 失敗且可重試。這是測試功能，生產設定不得帶入故障注入參數。

## 可觀察的 Mock 模擬時間

預設 CH0、CH1 使用以下時間，讓進度條可被肉眼觀察：

```yaml
mock:
  progress_steps: 30
  delays:
    erase: 1.5
    program: 3.0
    verify: 1.5
    read: 0.8
```

這些時間只代表空的 Mock 操作，不是 STM32 或 FPGA 的真實效能。未來接入 OpenOCD／FPGA 時，必須由實體介面回報真正完成的 byte count 或硬體狀態；不能沿用模擬百分比冒充真實進度。

## 已知限制

- 尚無身份驗證、TLS、權限模型或防重放機制。
- Job 狀態使用檔案保存，未導入 SQLite／PostgreSQL；高工作量下需重新評估。
- TCP 目前是一個 request 對一個 connection，尚未做長連線、多工與事件推送。
- Server 重啟可辨識未完成工作，但不會自動重做燒錄。
- OpenOCD binary staging、adapter isolation、port 配置與實體 target 尚未驗證。
- FPGA register map、AXI/FIFO、SWD engine、power-good 與安全關電尚未實作。
- ZIP 內附 React Web Console 原始碼，但仍屬 Web Mock／操作介面，不代表 Z2 實機燒錄已完成。

下一階段應先完成單通道 OpenOCD 實機燒錄，再做雙通道硬體隔離；不要直接跳到八個實體通道。
