# Plasma v3.1 通訊協定

## Domain naming compatibility

Plasma 的 canonical domain vocabulary 已統一為：

```text
Facility -> PPU (Plasma Programming Unit) -> Site (Programming Site)
```

但 Plasma protocol v3.1 在這次命名確立之前就已發布，因此 wire metadata 仍使用 `channel_id`。在 v3.1 中：

> `channel_id` 的語意就是「目前這台 PPU 內的 local Programming Site ID」。

這次 domain rename **不修改 v3.1 wire field，也不變更 protocol version**。新的 REST/domain code 使用 `site_id`，在 protocol boundary 轉成 `channel_id`。未來若要修改 wire field，必須以獨立且明確的 protocol-version migration 處理。

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
- `channel_id` 是 local Programming Site ID；名稱保留是 v3.1 compatibility requirement。
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
| `site_id` | canonical domain alias，對應同一個 local Site |
| `channel_id` | v3.1 compatibility field，與 `site_id` 指向同一 local Site |
| `stage` | `erase`、`program`、`verify` 或 read section |
| `stage_state` | `started`、`progress`、`completed`、`failed`、`cancelled` |
| `stage_progress_percent` | 目前階段 0～100% |
| `progress_percent` | 整個 Job 0～100% |
| `bytes_done` / `bytes_total` | 有 byte 語意的階段才提供 |
| `cancel_requested` | Server 是否已收到取消要求 |
| `updated_at` | 最後狀態更新時間 |

每個操作是獨立 Job。`program` 只寫入 Firmware，不會自動執行 `erase` 或 `verify`；需要完整燒錄流程時，Client 必須依序送出 `erase → program → verify`。每個 Job 的 `progress_percent` 分別由該操作的實際進度計算。

Request-level error：

```json
{
  "protocol_version": "3.1",
  "message_type": "response",
  "ok": false,
  "error": {
    "error_code": "E4002",
    "error_type": "CHANNEL_DISABLED",
    "message": "site is disabled: SITE7",
    "recoverable": false
  }
}
```

`CHANNEL_*` error type/code 也屬於既有 v3.1 compatibility surface；新的 domain terminology 是 Site，但錯誤碼不在這次 rename 中重新編號。

## v0.3.1 的連線模型

每個 TCP connection 傳送一個 request 並取得一個 response，之後關閉。這個模型容易驗證 frame boundary，但大量工作下會增加連線成本。未來若改成長連線，必須保留 frame header、`job_id` 和 request ID，不能假設 TCP `recv()` 一次就是一個 frame。
