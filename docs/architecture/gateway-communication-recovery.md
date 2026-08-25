# Gateway Communication and Recovery

## Scope

This document defines the current Plasma Web REST Gateway-to-PPU communication policy and the server-side Batch recovery boundary shared by PMode and EMode. It does not redefine the Plasma Protocol v3.3 Job timeout/retry policy or the Batch `site_retry_limit`; those are separate layers.

## Shared policy resource

The canonical resource is:

```text
GET  /api/settings/gateway
POST /api/settings/gateway
```

EMode exposes it at `Settings -> Gateway`. PMode consumes the same Gateway-side policy and does not maintain a second copy.

| Field | Default | Allowed range | Meaning |
|---|---:|---:|---|
| `ppu_request_timeout_ms` | 10000 | 1000–120000 | Deadline for one Gateway provider request. |
| `ppu_retry_count` | 3 | 0–10 | Additional attempts after a transient observation request failure. |
| `revision` | 1 | positive integer | Server-owned revision; clients cannot write it. |

When a persistence path is configured, settings are written atomically as YAML. A Batch snapshots the complete policy at creation; an update changes only future Batches.

## Retry boundary

Only transient timeout, OS/connection failure, `CONNECTION_TIMEOUT`, and `CONNECTION_FAILED` are retryable. Backoff is capped:

```text
1 s -> 2 s -> 4 s -> 4 s ...
```

Job `start` submission is intentionally not retried. A timeout after an unacknowledged submission has an ambiguous outcome, so resending could create a duplicate Job. After the Gateway receives an accepted `job_id`, status observation is retryable because it is idempotent.

Batch `site_retry_limit` is different: it controls retry of a trustworthy Site operation failure inside the PPU Job contract. Operators must not add the two retry counts together or interpret communication retry as another IC attempt.

## Failure containment

| Failure | Runtime action | Manufacturing accounting |
|---|---|---|
| One Site returns `failed`/`timeout` after Site retry | Mark the Site `FAULTED`; apply Batch failed-Site threshold. | Count one `FAIL` for the affected IC round. |
| Gateway observation retry is exhausted for one PPU | Mark trigger Site `ERROR`; mark that PPU failed; cancel active Jobs only on that PPU; prevent its remaining Sites from continuing. | Do not increment `FAIL`; state is infrastructure `ERROR`/`STOPPED`. |
| Operator presses ABORT | Set Batch `STOPPING`; cancel all active Jobs in the Batch; reconcile terminal states. | Cancelled work is not PASS or FAIL. |
| Failed-Site threshold is reached | Set Batch `STOPPING`; cancel all active Batch Jobs. | Existing PASS/FAIL remain; unprocessed work is stopped. |
| Unhandled Batch runtime exception | Mark Batch `ERROR`; stop remaining work. | Do not fabricate IC results. |

The current runtime therefore contains a single-PPU communication fault at the PPU boundary. It does not stop healthy PPUs merely because one PPU timed out. A whole-Batch ABORT remains an explicit operator action.

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

1. Record `batch_id`, Facility, PPU, Site, current `job_id`, policy revision and timestamps.
2. Distinguish submission failure (no accepted Job identity) from status-observation failure (accepted Job identity exists).
3. Check `communication_state` and `communication_attempt` before classifying the event.
4. Preserve `ERROR` as an infrastructure outcome; never convert it to IC `FAIL` merely to close a Batch.
5. If ABORT is requested, wait for Batch terminal reconciliation before switching product mode.
6. Treat a manual reconnect as transport recovery, not proof that an accepted Job stopped.
