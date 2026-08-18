# Plasma v3.2 通訊協定

## Canonical identity model

Plasma 的 canonical domain vocabulary 為：

```text
Facility -> PPU (Plasma Programming Unit) -> Site (Programming Site)
```

Protocol v3.2 把 wire identity 與產品／domain identity 統一：

```text
SITE 1 -> site_id = 1
SITE 2 -> site_id = 2
...
SITE N -> site_id = N
```

Canonical Site ID **從 1 開始**，不存在 `SITE 0`。新版 Web、REST、CLI、Python Server、log、read-back filename 與 wire protocol 都使用相同的 one-based `site_id`。

## v3.2 Frame 格式

每個 frame 由固定 20-byte header 加三段 payload 組成：

| 欄位 | 大小 | 格式 |
|---|---:|---|
| Magic | 8 bytes | ASCII `PLASMA32` |
| Metadata length | 4 bytes | unsigned big-endian |
| Map length | 4 bytes | unsigned big-endian |
| Binary length | 4 bytes | unsigned big-endian |
| Metadata | variable | UTF-8 JSON object |
| Map | variable | UTF-8 JSON object；可為空 |
| Binary | variable | raw bytes；可為空 |

Header 的 Python 定義仍是 `struct.Struct("!8sIII")`。Receiver 必須先檢查三段長度上限，再配置或讀取 payload。

Magic 與 metadata 版本必須一致：`PLASMA32` 必須搭配 `protocol_version: "3.2"`；`PLASMA31` 必須搭配 `3.1`。版本／Magic 混用會被視為 protocol error。

## v3.2 Request metadata

工作 request 範例：

```json
{
  "protocol_version": "3.2",
  "message_type": "request",
  "job_id": "job-20260818-123456-abcdef12",
  "site_id": 1,
  "operation": "program",
  "timeout_s": 30.0,
  "max_retries": 1,
  "retry_backoff_s": 0.05,
  "client_id": "plasma-cli",
  "target": "STM32F103C8T6",
  "firmware_name": "firmware.bin",
  "firmware_size": 65536,
  "firmware_sha256": "...",
  "wait_for_completion": false
}
```

Server 檢查：

- `protocol_version` 必須是支援版本。
- v3.2 必須使用正整數 `site_id >= 1`，不得同時傳 `channel_id`。
- `firmware_size` 必須等於 header 的 BINLEN。
- `firmware_sha256` 必須等於實際 binary SHA-256。
- metadata／map 必須是 JSON object。
- payload 不得超過設定上限。
- `job_id` 必須是 1～128 個 ASCII 字母、數字、`.`、`_` 或 `-`，且第一個字元必須是字母或數字。
- `wait_for_completion` 必須是 JSON boolean，不能使用字串 `"false"` 代替。
- 自訂 metadata 不得覆寫 `job_id`、`site_id`、`operation`、長度、checksum 等保留欄位。

## v3.2 Response

通訊成功與 Job 成功是兩個不同概念。Server 正常接受並完成一個「燒錄失敗」工作時，response 的 `ok` 仍可為 `true`，但 `result.state` 是 `failed`。`ok=false` 代表 request／protocol／routing 本身無法成立。

成功：

```json
{
  "protocol_version": "3.2",
  "message_type": "response",
  "ok": true,
  "result": {
    "job_id": "...",
    "site_id": 1,
    "state": "success"
  }
}
```

非阻塞提交成功時先回覆：

```json
{
  "protocol_version": "3.2",
  "message_type": "response",
  "ok": true,
  "accepted": true,
  "job": {
    "job_id": "job-...",
    "site_id": 1,
    "state": "queued",
    "progress_percent": 0.0
  }
}
```

之後以 `status` 查詢，v3.2 Job snapshot 包含 canonical `site_id`，不再附帶 `channel_id`。主要欄位：

| 欄位 | 意義 |
|---|---|
| `site_id` | one-based local Programming Site ID |
| `stage` | `erase`、`program`、`verify` 或 read section |
| `stage_state` | `started`、`progress`、`completed`、`failed`、`cancelled` |
| `stage_progress_percent` | 目前階段 0～100% |
| `progress_percent` | 整個 Job 0～100% |
| `bytes_done` / `bytes_total` | 有 byte 語意的階段才提供 |
| `cancel_requested` | Server 是否已收到取消要求 |
| `updated_at` | 最後狀態更新時間 |

每個操作是獨立 Job。`program` 只寫入 Firmware，不會自動執行 `erase` 或 `verify`；需要完整燒錄流程時，Client 必須依序送出 `erase → program → verify`。

Request-level Site error：

```json
{
  "protocol_version": "3.2",
  "message_type": "response",
  "ok": false,
  "error": {
    "error_code": "E4002",
    "error_type": "SITE_DISABLED",
    "message": "site is disabled: SITE8",
    "recoverable": false
  }
}
```

E4001/E4002/E4003 數值保留，但 v3.2 canonical error names 為 `SITE_INVALID`、`SITE_DISABLED`、`SITE_BUSY`。

## v3.1 compatibility boundary

Protocol v3.1 仍可在過渡期間被 Server 接受，但它是 legacy adapter，不是新的 domain contract：

```text
v3.1 wire                  canonical domain / v3.2
PLASMA31                    PLASMA32
channel_id = 0      ->      site_id = 1
channel_id = 1      ->      site_id = 2
...
channel_id = N-1    ->      site_id = N
```

v3.1 request 必須使用 `channel_id`，不得使用 `site_id`；Server 依 request protocol version 回覆相同版本。v3.1 STATUS 保留 `programmer/channels` shape，v3.1 Job/result 使用 `channel_id`，v3.1 Site errors 序列化成 `CHANNEL_INVALID`、`CHANNEL_DISABLED`、`CHANNEL_BUSY`。

Legacy `channels:` 設定檔也只在 config loader 邊界做相同的 `0 -> 1` translation；進入 canonical Python domain 後，不應再存在 Site 0。

## Connection model

每個 TCP connection 傳送一個 request 並取得一個 response，之後關閉。這個模型容易驗證 frame boundary，但大量工作下會增加連線成本。未來若改成長連線，必須保留 frame header、`job_id` 和 request ID，不能假設 TCP `recv()` 一次就是一個 frame。
