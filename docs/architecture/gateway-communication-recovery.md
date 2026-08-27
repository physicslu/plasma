# Gateway Communication and Recovery

## Scope

This document defines the Plasma Web REST Gateway-to-PPU communication policy and the server-side recovery boundary shared by PMode and EMode. It does not redefine the Plasma Protocol v3.3 Job timeout/retry policy or the Batch `site_retry_limit`; those are separate layers.

The ownership rule is explicit:

```text
Browser / UI
    -> observes Gateway responses and presents reconnect state

Plasma Web REST Gateway
    -> owns PPU request deadline, retry count, communication backoff,
       stable communication errors, and the declared response budget

PPU
    -> executes the requested status / Job operation
```

A browser transport watchdog must never expire before the Gateway has had enough time to complete its declared PPU communication policy.

## Shared policy resource

The canonical resource is:

```text
GET  /api/settings/gateway
POST /api/settings/gateway
```

EMode exposes the writable settings at `Settings -> Gateway`. PMode consumes the same Gateway-side policy and does not maintain a second PPU timeout/retry policy.

| Field | Default | Allowed range | Meaning |
|---|---:|---:|---|
| `ppu_request_timeout_ms` | 10000 | 1000–120000 | Deadline for one Gateway-to-PPU provider attempt. |
| `ppu_retry_count` | 3 | 0–10 | Additional attempts after a transient retryable observation failure. |
| `revision` | 1 | positive integer | Server-owned revision; clients cannot write it. |
| `ppu_response_budget_ms` | 47000 | derived | Read-only upper bound for the complete Gateway observation request, including configured attempts and communication backoff. |

`ppu_response_budget_ms` is derived by the Gateway and is not persisted or accepted in the settings POST body. With the default policy, four 10-second attempts plus 1 s, 2 s, and 4 s backoff produce a 47-second response budget.

When a persistence path is configured, only `revision`, `ppu_request_timeout_ms`, and `ppu_retry_count` are written atomically as YAML. A Batch snapshots the complete persistent policy at creation; an update changes only future Batches. Direct Engineering status observations read the current Gateway policy for each HTTP request.

## Status observation boundary

Canonical Engineering status requests are:

```text
GET /api/engineering/targets/{facility_id}/{ppu_id}/api/status
GET /api/engineering/targets/{facility_id}/{ppu_id}/api/status?site={site_id}&job={job_id}
```

These routes execute PPU communication inside the Gateway policy boundary. The Browser does not apply its own PPU attempt timeout or retry count.

For transient communication failures, the Gateway retries the provider call before returning an HTTP response. When retries are exhausted, the Gateway returns `503 Service Unavailable` with the stable communication error code:

```text
E2001 CONNECTION_FAILED
E2002 CONNECTION_TIMEOUT
```

PMode may perform a later background status re-probe after one complete Gateway request has failed. That UI recovery loop is a new observation request; it is not another IC attempt, does not increment manufacturing retry statistics, and does not replace the Gateway's PPU communication retry ownership.

The browser still has an HTTP transport watchdog to detect a Gateway/public-path request that never completes. Its deadline is derived from `ppu_response_budget_ms` plus a transport margin. The margin exists only to prevent an outer browser timeout from racing the authoritative Gateway policy.

## Response-boundary diagnostics

PPU-level Engineering status diagnostics separate the provider phase from the Gateway HTTP response-write phase. The normal sequence is:

```text
engineering_ppu_status_start
engineering_ppu_status_ok
engineering_ppu_status_response_sent
```

The fields `provider_elapsed_ms`, `response_write_elapsed_ms`, and `total_elapsed_ms` allow the two phases to be distinguished.

The semantics are deliberately narrow:

- `engineering_ppu_status_ok` means the Gateway obtained a PPU/provider payload successfully. It does **not** prove that the HTTP response was written successfully or received by the Browser.
- `engineering_ppu_status_response_sent` means the Gateway handler's response-write call returned successfully. It does **not** prove that Vite, Cloudflare/public ingress, or the Browser received or acknowledged the response.
- `engineering_ppu_status_response_error` means the provider phase succeeded but the Gateway response-write call raised an exception. The diagnostic includes `error_type` plus provider/write/total timing.
- `engineering_ppu_status_error` remains a provider/PPU communication failure; response-write failures must not be misclassified as PPU failures.

A response-write failure therefore has this diagnostic sequence:

```text
engineering_ppu_status_start
engineering_ppu_status_ok
engineering_ppu_status_response_error
request_error
```

These events are intentionally PPU-level observation diagnostics. Job-specific status observation does not emit the same PPU-level noise.

The current diagnostics do not provide a per-request correlation ID. Timestamp ordering is useful operational evidence but must not be treated as mathematical proof that two independently observed log/browser events belong to the same request. A future correlation identifier may improve this boundary without changing communication policy.

## Retry boundary

Only transient timeout, OS/connection failure, `CONNECTION_TIMEOUT`, and `CONNECTION_FAILED` are retryable. Gateway communication backoff is capped:

```text
1 s -> 2 s -> 4 s -> 4 s ...
```

Job `start` submission is intentionally not retried. A timeout after an unacknowledged submission has an ambiguous outcome, so resending could create a duplicate Job. After the Gateway receives an accepted `job_id`, status observation is idempotent and may be retried.

Batch `site_retry_limit` is different: it controls retry of a trustworthy Site operation failure inside the PPU Job contract. Operators and software must not add communication retry counts to Site retry counts or interpret communication recovery as another IC programming attempt.

## Failure containment

| Failure | Runtime action | Manufacturing accounting |
|---|---|---|
| One Site returns `failed`/`timeout` after Site retry | Mark the Site `FAULTED`; apply Batch failed-Site threshold. | Count one `FAIL` for the affected IC round. |
| Gateway observation retry is exhausted for one PPU during Batch execution | Mark trigger Site `ERROR`; mark that PPU failed; cancel active Jobs only on that PPU; prevent its remaining Sites from continuing. | Do not increment `FAIL`; state is infrastructure `ERROR`/`STOPPED`. |
| Pre-Batch PPU status observation exhausts Gateway retries | Return `503/E2001` or `503/E2002`; UI marks communication degraded and may re-probe later. | No manufacturing result exists yet. |
| Operator presses ABORT | Set Batch `STOPPING`; cancel all active Jobs in the Batch; reconcile terminal states. | Cancelled work is not PASS or FAIL. |
| Failed-Site threshold is reached | Set Batch `STOPPING`; cancel all active Batch Jobs. | Existing PASS/FAIL remain; unprocessed work is stopped. |
| Unhandled Batch runtime exception | Mark Batch `ERROR`; stop remaining work. | Do not fabricate IC results. |

The runtime contains a single-PPU communication fault at the PPU boundary. It does not stop healthy PPUs merely because one PPU timed out. A whole-Batch ABORT remains an explicit operator action.

## Execution and mode-switch guard

The browser may release the PMode/EMode navigation guard only after the Batch is terminal. A Site card showing `ERROR` is not sufficient by itself: Jobs already accepted by the PPU may still exist, and cancellation/terminal observation must be reconciled.

The server-side Batch states that block mode switching are:

```text
QUEUED
RUNNING
STOPPING
```

Terminal states include `SUCCESS`, `PARTIAL`, `ERROR`, and `CANCELLED`. A reconnect restores observation; it must not invent a terminal result. Backend cross-client execution ownership remains separately tracked in the [Development Debt Register](../development/todo.md).

## Diagnostics checklist

1. Record `batch_id` when applicable, Facility, PPU, Site, current `job_id`, policy revision and timestamps.
2. Distinguish submission failure (no accepted Job identity) from status-observation failure (accepted Job identity may exist).
3. For PPU-level Engineering observation, correlate `engineering_ppu_status_start`, optional `engineering_ppu_status_retry`, `engineering_ppu_status_ok` / `engineering_ppu_status_error`, and the response-boundary event `engineering_ppu_status_response_sent` / `engineering_ppu_status_response_error`.
4. If `engineering_ppu_status_error` occurs, investigate the PPU/provider communication path and the Gateway retry classification before blaming the public path.
5. If `engineering_ppu_status_ok` is followed by `engineering_ppu_status_response_error`, the provider completed but the Gateway response-write boundary failed; do not classify that incident as a PPU programming failure.
6. If `engineering_ppu_status_ok` and `engineering_ppu_status_response_sent` are both present but the Browser still times out, the Gateway provider and handler response-write call both completed. Investigate the downstream Vite proxy / public ingress / Browser fetch path without claiming any one component as root cause until evidence identifies it.
7. If `engineering_ppu_status_ok` appears without either response-boundary event, inspect the Gateway handler/write path and confirm the deployed version before drawing conclusions.
8. Check `communication_state` and `communication_attempt` before classifying a Batch event.
9. Preserve `ERROR` as an infrastructure outcome; never convert it to IC `FAIL` merely to close a Batch.
10. If ABORT is requested, wait for Batch terminal reconciliation before switching product mode.
11. Treat a manual reconnect as transport recovery, not proof that an accepted Job stopped.
