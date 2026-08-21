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

Web REST v3 接收 **Programming Asset**；Protocol v3.3 不傳送來源 Asset model，而傳送或引用已經解析/正規化後的 **Image execution data**。

```text
Programming Asset
    |
    | parser / normalizer
    v
Normalized Image
    |
    | Protocol v3.3
    +--------------------------+
    |                          |
    v                          v
inline Binary              execution_image_ref
(real/default path)        (local Mock optimization)
    |                          |
    +------------+-------------+
                 v
             PPU execution
```

Canonical execution identity仍使用：

```text
image_size
image_sha256
```

而不是來源檔案的 Asset 欄位。

`execution_image_ref` 是 additive execution transport contract，不是 Programming Asset identity。Phase 1 只支援同一個 Mock runtime 已存在的 content-addressed Blob；真實 PPU 與不支援 reference 的介面仍使用 inline binary。

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
| Binary | variable | inline normalized Image bytes；使用 reference 時必須為空 |

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

### Inline Program request

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

Inline request 的 normalized Image bytes 放在 frame Binary payload。

### Local Mock execution-image reference

當 normalized Image 已存在同一個 local Mock runtime 的 Shared Image Store 時，Program/Verify 可選擇不再攜帶 Binary payload，而改送：

```json
{
  "protocol_version": "3.3",
  "message_type": "request",
  "job_id": "job-20260821-123456-abcdef12",
  "site_id": 1,
  "operation": "program",
  "image_size": 4194304,
  "image_sha256": "<64-hex-sha256>",
  "execution_image_ref": {
    "scheme": "local_mock_blob",
    "sha256": "<64-hex-sha256>",
    "size_bytes": 4194304
  }
}
```

Reference contract 的限制：

- reference 與 Binary payload 互斥。
- reference 只描述 content identity；不得攜帶 filesystem path。
- `image_size` 必須等於 reference `size_bytes`。
- `image_sha256` 必須等於 reference `sha256`。
- Phase 1 `local_mock_blob` 只供 local Mock execution 使用，不是跨主機 Blob protocol。
- Real PPU 不需要實作此 scheme；既有 inline binary path 保持 canonical supported path。

Server checks：

- `protocol_version` 必須為 `3.3`。
- `site_id` 必須是 JSON integer 且 `>= 1`。
- Inline mode：`image_size` 必須等於 header BINLEN，`image_sha256` 必須等於 Binary payload SHA-256。
- Reference mode：BINLEN 必須為 0，`image_size/image_sha256` 必須和 `execution_image_ref` 一致。
- metadata/map 必須是 JSON object。
- payload 不得超過設定上限。
- `job_id` 必須符合 canonical ID 規則。
- `wait_for_completion` 必須是 JSON boolean。
- 自訂 metadata 不得覆寫保留 protocol fields。

Local Mock Server 收到既有 inline Program/Verify request 後，可在 ingress 將 Image content-address 化並把 JobRuntime 轉成 `execution_image_ref`，因此 queue/retry/JobRegistry 不必長期保留每個 Job 的完整 Image bytes。這個最佳化不改變 client 原本的 inline request contract。

## Response

通訊成功與 Job 成功是不同概念。Request/protocol/routing 成立時 `ok=true`；Job 本身仍可能以 `failed/error/cancelled/timeout/aborted` 結束。

其中：

```text
failed     target/operation outcome failed
error      execution infrastructure failed
cancelled  operator/client cancellation won terminal state
```

`timeout` 與 `aborted` 目前保留為既有 Protocol v3.3 terminal states。

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
| `stage_state` | started/progress/completed/failed/error/cancelled |
| `stage_progress_percent` | 目前 stage 0–100% |
| `progress_percent` | Job 0–100% |
| `bytes_done` / `bytes_total` | byte-oriented stage progress |
| `attempt` | 目前/最後執行 attempt，從 1 開始 |
| `attempt_history` | 每次 attempt 的結果、時間、error 與是否排定 retry |
| `retry_exhausted` | recoverable failure 是否已耗盡 `max_retries` |
| `cancel_requested` | Server 是否收到取消要求 |
| `updated_at` | 最後狀態更新時間 |

`max_retries = N` 的 canonical 語意是：

```text
1 initial attempt + at most N retry attempts
```

因此 `max_retries = 2` 最多執行 3 次。這個 attempt provenance 是後續 Batch `Site FAULTED` / retry-exhaustion policy 的底層 contract。

每個 operation 是獨立 Job。`program` 只寫入 Image，不會隱含 `erase` 或 `verify`。完整流程由 Client 明確組合：

```text
erase -> program -> verify
```

## Failure-source taxonomy

`ErrorDetail.failure_source` 用來區分「Job 為什麼失敗」，避免所有問題都被統計成 IC/operation fail。

目前 canonical values：

| failure_source | 意義 |
|---|---|
| `injected` | Mock fault injection |
| `mismatch` | Verify data mismatch |
| `infrastructure` | transport/interface/internal/output 等執行基礎設施問題 |
| `cancelled` | cancellation |
| `operation` | 一般 operation failure，producer 沒有更精確分類 |

Infrastructure failure 對應 Job `error`，不得假裝成 Programming yield `failed`。

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
