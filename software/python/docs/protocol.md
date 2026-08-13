# Plasma v3.1 通訊協定

## Frame 格式

每個 frame 由固定 20-byte header 加三段 payload 組成：

| 欄位 | 大小 | 格式 |
|---|---:|---|
| Magic | 8 bytes | ASCII `PLASMA31` |
| Metadata length | 4 bytes | unsigned big-endian |
| Map length | 4 bytes | unsigned big-endian |
| Binary length | 4 bytes | unsigned big-endian |
| Metadata | variable | UTF-8 JSON object |
| Map | variable | UTF-8 JSON object；可為空 |
| Binary | variable | raw bytes；可為空 |

Header 的 Python 定義是 `struct.Struct("!8sIII")`。Receiver 必須先檢查三段長度上限，再配置或讀取 payload。

## Request metadata

工作 request 範例：

```json
{
  "protocol_version": "3.1",
  "message_type": "request",
  "job_id": "job-20260808-123456-abcdef12",
  "channel_id": 0,
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

Server 同時檢查：

- `protocol_version` 必須是 `3.1`。
- `firmware_size` 必須等於 header 的 BINLEN。
- `firmware_sha256` 必須等於實際 binary SHA-256。
- metadata／map 必須是 JSON object。
- payload 不得超過設定上限。
- `job_id` 必須是 1～128 個 ASCII 字母、數字、`.`、`_` 或 `-`，且第一個字元必須是字母或數字。
- `wait_for_completion` 必須是 JSON boolean，不能使用字串 `"false"` 代替。
- 自訂 metadata 不得覆寫 `job_id`、`channel_id`、`operation`、長度、checksum 等保留欄位。

## Response

通訊成功與 Job 成功是兩個不同概念。Server 正常接受並完成一個「燒錄失敗」工作時，response 的 `ok` 仍可為 `true`，但 `result.state` 是 `failed`。`ok=false` 代表 request／protocol／routing 本身無法成立。

成功：

```json
{
  "protocol_version": "3.1",
  "message_type": "response",
  "ok": true,
  "result": {
    "job_id": "...",
    "state": "success"
  }
}
```

非阻塞提交成功時先回覆：

```json
{
  "protocol_version": "3.1",
  "message_type": "response",
  "ok": true,
  "accepted": true,
  "job": {
    "job_id": "job-...",
    "state": "queued",
    "progress_percent": 0.0
  }
}
```

之後以 `status` 查詢，Job snapshot 會包含：

| 欄位 | 意義 |
|---|---|
| `stage` | `erase`、`program`、`verify` 或 read section |
| `stage_state` | `started`、`progress`、`completed`、`failed`、`cancelled` |
| `stage_progress_percent` | 目前階段 0～100% |
| `progress_percent` | 整個 Job 0～100% |
| `bytes_done` / `bytes_total` | 有 byte 語意的階段才提供 |
| `cancel_requested` | Server 是否已收到取消要求 |
| `updated_at` | 最後狀態更新時間 |

`program` 的三個階段目前各占整體進度三分之一。這是 Mock 工作流程權重；真實硬體版應根據 erase block、傳輸 byte count 與 verify 回報重新定義。

Request-level error：

```json
{
  "protocol_version": "3.1",
  "message_type": "response",
  "ok": false,
  "error": {
    "error_code": "E4002",
    "error_type": "CHANNEL_DISABLED",
    "message": "channel is disabled: CH7",
    "recoverable": false
  }
}
```

## v0.3.1 的連線模型

每個 TCP connection 傳送一個 request 並取得一個 response，之後關閉。這個模型容易驗證 frame boundary，但大量工作下會增加連線成本。未來若改成長連線，必須保留 frame header、`job_id` 和 request ID，不能假設 TCP `recv()` 一次就是一個 frame。
