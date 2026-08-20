# Plasma v3.3 通訊協定

## Canonical identity model

Plasma canonical domain vocabulary：

```text
Facility -> PPU (Plasma Programming Unit) -> Site (Programming Site)
```

Protocol v3.3 使用 one-based Site identity：

```text
SITE 1 -> site_id = 1
SITE 2 -> site_id = 2
...
SITE N -> site_id = N
```

不存在 canonical `SITE 0`。

## Programming data boundary

Web REST v3 接收 **Programming Asset**；Protocol v3.3 不傳送來源 Asset model，而傳送已經解析/正規化後的 **Image** execution data。

```text
Programming Asset
    |
    | parser / normalizer
    v
Normalized Image
    |
    | Protocol v3.3
    v
PPU execution
```

因此 wire metadata 使用：

```text
image_size
image_sha256
```

而不是來源檔案的 Asset 欄位。

## Frame format

每個 frame 由固定 20-byte header 加三段 payload 組成：

| 欄位 | 大小 | 格式 |
|---|---:|---|
| Magic | 8 bytes | ASCII `PLASMA33` |
| Metadata length | 4 bytes | unsigned big-endian |
| Map length | 4 bytes | unsigned big-endian |
| Binary length | 4 bytes | unsigned big-endian |
| Metadata | variable | UTF-8 JSON object |
| Map | variable | UTF-8 JSON object；可為空 |
| Binary | variable | normalized Image bytes；可為空 |

Header Python definition：

```python
struct.Struct("!8sIII")
```

Receiver 必須先檢查三段長度上限，再讀取 payload。

Canonical magic/version 必須一致：

```text
PLASMA33 <-> protocol_version: "3.3"
```

舊 protocol version 不是目前 canonical runtime contract。

## Request metadata

Program request 範例：

```json
{
  "protocol_version": "3.3",
  "message_type": "request",
  "job_id": "job-20260820-123456-abcdef12",
  "site_id": 1,
  "operation": "program",
  "timeout_s": 30.0,
  "max_retries": 1,
  "retry_backoff_s": 0.05,
  "client_id": "plasma-cli",
  "target": "STM32F103C8T6",
  "image_name": "application.bin",
  "image_size": 65536,
  "image_sha256": "...",
  "wait_for_completion": false
}
```

Server checks：

- `protocol_version` 必須為 `3.3`。
- `site_id` 必須是 JSON integer 且 `>= 1`。
- `image_size` 必須等於 header BINLEN。
- `image_sha256` 必須等於實際 normalized Image SHA-256。
- metadata/map 必須是 JSON object。
- payload 不得超過設定上限。
- `job_id` 必須符合 canonical ID 規則。
- `wait_for_completion` 必須是 JSON boolean。
- 自訂 metadata 不得覆寫保留 protocol fields。

## Response

通訊成功與 Job 成功是不同概念。Request/protocol/routing 成立時 `ok=true`；Job 本身仍可能以 `failed/cancelled/timeout` 結束。

成功：

```json
{
  "protocol_version": "3.3",
  "message_type": "response",
  "ok": true,
  "result": {
    "job_id": "...",
    "site_id": 1,
    "state": "success",
    "image_size": 65536,
    "image_sha256": "..."
  }
}
```

非阻塞提交：

```json
{
  "protocol_version": "3.3",
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

主要 Job snapshot fields：

| 欄位 | 意義 |
|---|---|
| `site_id` | one-based local Programming Site ID |
| `stage` | erase/program/verify/read section |
| `stage_state` | started/progress/completed/failed/cancelled |
| `stage_progress_percent` | 目前 stage 0–100% |
| `progress_percent` | Job 0–100% |
| `bytes_done` / `bytes_total` | byte-oriented stage progress |
| `cancel_requested` | Server 是否收到取消要求 |
| `updated_at` | 最後狀態更新時間 |

每個 operation 是獨立 Job。`program` 只寫入 Image，不會隱含 `erase` 或 `verify`。完整流程由 Client 明確組合：

```text
erase -> program -> verify
```

## Site errors

範例：

```json
{
  "protocol_version": "3.3",
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

Canonical Site error names：

```text
SITE_INVALID
SITE_DISABLED
SITE_BUSY
```

## Connection model

每個 TCP connection 目前傳送一個 request 並取得一個 response，之後關閉。這個模型容易驗證 frame boundary，但大量工作會增加 connection overhead。

未來若改成 persistent connection，仍必須保留明確 frame header、Job/request identity 與 payload boundary，不能假設一次 TCP `recv()` 等於一個完整 frame。
