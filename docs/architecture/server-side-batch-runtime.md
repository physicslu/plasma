# Plasma Server-side Batch Runtime

Status: Phase 1 execution contract

## Purpose

Production Mode must not own manufacturing execution semantics in the browser. A Batch is a server-side execution object with an immutable execution policy and a fixed target/operation/Programming Asset snapshot.

Canonical hierarchy:

```text
Facility -> PPU -> Site
```

A Site is the independent execution unit. Different Sites and PPUs do not wait for each other.

## Batch execution policy

```text
repeat_count
site_retry_limit
failed_site_stop_threshold
```

### `repeat_count`

The complete selected operation sequence is one round.

For operations `Erase -> Program -> Verify` and `repeat_count = 3`:

```text
Round 1: Erase -> Program -> Verify
Round 2: Erase -> Program -> Verify
Round 3: Erase -> Program -> Verify
```

There is no global round barrier. A Site that completes Round 1 may begin Round 2 immediately even if another Site is still in Round 1.

### `site_retry_limit`

This value is the number of retries after the first attempt.

```text
site_retry_limit = 0 -> at most 1 attempt
site_retry_limit = 1 -> at most 2 attempts
site_retry_limit = 2 -> at most 3 attempts
```

Phase 1 uses one Batch-level retry limit for every selected operation. The Batch Runtime passes this policy into the canonical Job `max_retries` contract; it does not implement a second retry engine.

If a recoverable operation failure consumes all allowed retries, that Site becomes `FAULTED` and does not start later operations or rounds in the same Batch.

### `failed_site_stop_threshold`

This is a Batch circuit-breaker threshold. `null` disables the threshold.

The stop rule is inclusive:

```text
faulted_site_count >= failed_site_stop_threshold
```

For threshold `3`, the third `FAULTED` Site trips the Batch circuit breaker. The triggering Site remains `FAULTED`; other in-flight Jobs receive cancel requests and remaining Sites stop without rewriting already-completed results.

The Batch terminates as `ERROR` with stop reason `failed_site_threshold`.

## Failure taxonomy

Batch, Site and Job states are separate layers.

| Condition | Job | Site | Batch effect |
|---|---|---|---|
| operation succeeds | `SUCCESS` | continues | continues |
| recoverable operation failure succeeds after retry | `SUCCESS` | continues | continues |
| retry exhausted | `FAILED` / `TIMEOUT` | `FAULTED` | continues until threshold |
| PPU infrastructure failure | `ERROR` / `ABORTED` | `ERROR` | failed PPU stops; other PPUs continue |
| mixed PPU infrastructure failure and healthy PPU completion | mixed | `ERROR` / `SUCCESS` | Batch `PARTIAL` |
| operator Batch cancel | `CANCELLED` | `CANCELLED` or already-terminal state | Batch `CANCELLED` |
| threshold stop reaches another running Site | cancelled Job | `STOPPED` | Batch `ERROR` |

Infrastructure errors are not counted as IC/Site yield failures and do not increment `faulted_site_count`.

### Gateway communication policy and PPU fault containment

`GET /api/settings/gateway` exposes the server-owned communication policy and
`POST /api/settings/gateway` updates it atomically. Production and Engineering
share the same persisted settings. Defaults are:

```text
ppu_request_timeout_ms = 10000
ppu_retry_count        = 3
retry backoff          = 1 s, 2 s, 4 s, then capped at 4 s
```

Each Batch records one immutable `gateway_settings` snapshot containing the
settings revision, request timeout, and retry count. Changing Gateway settings
during execution cannot mutate a running Batch.

Read-only PPU status and idempotent Job cancellation may retry transient
transport failures. Job submission is never blindly retried because a timed-out
accept response does not prove that the PPU failed to enqueue the Job.

During retry, a Site exposes `communication_state = reconnecting` and
`communication_attempt`. Exhausting retry isolates the canonical
`(facility_id, ppu_id)` failure domain: the failed Site becomes `ERROR`,
unfinished sibling Sites become `STOPPED`, and only active Jobs owned by the
same Batch and PPU receive cancellation. Other PPUs continue.

A Batch containing both successful and infrastructure-error Sites ends as
`PARTIAL`; a Batch with infrastructure error and no successful Sites ends as
`ERROR`. Explicit operator Batch cancellation remains the only normal
whole-Batch stop action, apart from the separately configured manufacturing
failure-threshold circuit breaker.

## Programming Asset invariant

One Batch may bind at most one Programming Asset for Program/Verify. The Asset identity is fixed before execution begins and is cached to each participating PPU before the Batch worker thread starts.

Phase 1 stores this provenance in the Batch snapshot:

```text
name
asset_type
asset_format
size_bytes
sha256
```

The server-side Batch API accepts the Asset once at Batch creation. Per-Site/round Jobs reference the cached Asset by SHA instead of asking the browser to resend or reselect a file.

## Statistics

Statistics are separated into logical executions and physical attempts.

Per operation:

```text
logical_executions
attempts
retries
successful_executions
failed_executions
error_executions
cancelled_executions
failed_attempts
error_attempts
cancelled_attempts
attempt_failure_rate
```

This separation is required because retry can recover an operation while still producing failed attempts. A low final operation failure rate must not hide contact/intermittent failure behavior.

Each Site also exposes:

```text
current_round
completed_rounds
current_operation
current_job_id
progress_percent
total_attempts
retry_count
final_failures
faulted_round
faulted_operation
last_failure_source
communication_state
communication_attempt
```

## REST contract

Phase 1 endpoints:

```text
POST /api/batches
GET  /api/batches/{batch_id}
POST /api/batches/{batch_id}/cancel
POST /api/batches/{batch_id}/targets/{facility_id}/{ppu_id}/cancel
```

Batch creation example:

```json
{
  "session_id": "...",
  "targets": [
    {
      "facility_id": "mock-facility-01",
      "ppu_id": "mock-facility-01-ppu-04",
      "site_ids": [1, 2, 3, 4]
    }
  ],
  "operations": ["erase", "program", "verify"],
  "execution_policy": {
    "repeat_count": 10,
    "site_retry_limit": 2,
    "failed_site_stop_threshold": 3
  },
  "asset": {
    "asset_name": "application.bin",
    "asset_type": "image",
    "asset_format": "binary",
    "asset_size": 4194304,
    "asset_sha256": "...",
    "asset_base64": "..."
  }
}
```

The response is `202 Accepted` and contains a server-generated Batch ID plus the initial Batch snapshot. Clients observe execution by polling the Batch resource rather than polling and sequencing every Site Job themselves.

## Current provider boundary

The Batch Runtime consumes a provider-shaped execution boundary (`status`, `start_job`, `cancel_job`, Asset cache and timeout lookup). In Phase 1 the server-side Engineering Mock Provider is the available multi-PPU backend.

This is intentionally not a claim that the current Mock Provider is the final production fleet transport. The Batch policy/state machine is provider-independent; a real fleet/Manager execution adapter can implement the same boundary later without moving Batch policy back into the browser.

## Deferred work

Not part of this Phase 1 runtime PR:

- Production UI migration from browser-owned `Promise.all` orchestration to `/api/batches`
- Mock Profile UI and deterministic fault-profile binding
- `minimum_active_sites`
- per-operation retry limits
- persistent Batch database / restart recovery
- cross-host Programming Asset distribution service
- Blob TTL/LRU/GC

These are separate changes so the execution engine and operator UI can be validated independently.
