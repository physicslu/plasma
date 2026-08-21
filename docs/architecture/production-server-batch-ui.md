# Production UI Server-side Batch Ownership

Status: implementation contract for the Production UI migration after PR #90.

## First principle

Production Mode is an operator client. It selects the execution set and policy, submits one Batch, observes server state, and requests cancellation. It does not sequence Site Jobs.

```text
Browser Production UI
    |
    | POST /api/batches
    v
Plasma Web REST Gateway
    |
    | authoritative Batch Runtime
    v
Facility -> PPU -> Site Jobs
```

The browser must not implement an alternate execution engine with `Promise.all`, per-Site Job sequencing, retry loops, or failed-Site threshold logic.

## Browser responsibilities

The Production UI owns:

- FPS selection (`Facility -> PPU -> Site`)
- selected EPVR operation set
- one Programming Asset selection
- BatchExecutionPolicy input
- one Batch submission
- Batch resource polling
- Batch cancel request
- PPU-scoped Batch cancel request
- operator display and logs

The Gateway Batch Runtime owns:

- Batch ID
- immutable operation order
- immutable Programming Asset provenance
- repeat rounds
- Site retry policy
- Site `FAULTED` transition
- failed-Site circuit breaker
- Batch terminal classification
- Site/Operation/Attempt statistics

## Execution state definitions

These definitions are operator-facing contract and must later appear unchanged in the user/operator manual.

### `FAULTED`

The Site executed a manufacturing operation, exhausted the configured retry budget, and did not pass. This is an execution/yield failure. It increments `faulted_site_count` and participates in `failed_site_stop_threshold`.

Example:

```text
Program attempt 1 -> FAILED
Program retry 1   -> FAILED
Program retry 2   -> FAILED
retry exhausted   -> Site FAULTED
```

### `ERROR`

The system cannot produce a reliable manufacturing result because infrastructure or control-plane execution failed. Examples include PPU/provider unavailability, protocol/infrastructure exceptions, or corrupted execution prerequisites. `ERROR` is not an IC yield failure and does not increment `faulted_site_count`.

### `STOPPED`

The Site did not finish because a Batch-level policy stopped future/in-flight work, for example after the failed-Site threshold was reached. `STOPPED` must not be rewritten as `FAULTED` because the Site itself did not necessarily fail.

### `CANCELLED`

Execution was cancelled by operator intent (Batch or PPU scoped). Cancellation is not a Site yield failure.

## Batch execution policy

Production exposes the canonical policy directly:

```text
repeat_count
site_retry_limit
failed_site_stop_threshold
```

- `repeat_count >= 1`
- `site_retry_limit` is retries after the first attempt
- blank `failed_site_stop_threshold` means disabled
- threshold semantics are inclusive: `faulted_site_count >= threshold`

## Programming Asset

Program/Verify use one immutable file snapshot per Batch. For the current Mock runtime, the Production UI accepts an image up to 4 MiB. The browser sends the Asset once when creating the Batch. The Gateway/Mock provider then uses the shared-image execution path added in PR #90; the browser never re-sends the image per Site or per round.

## Mode-switch guard

Engineering single-Site execution still contributes Job activity. Production server-side execution contributes Batch activity. Global navigation is locked while either activity count is non-zero.

This is required because moving orchestration out of the browser removes the old per-Job browser activity signals.

## Browser reload

The active Production `batch_id` is stored in `sessionStorage` as a reconnect hint. If the page reloads while the Gateway process remains alive, the UI queries the stored Batch resource and resumes observation. This is not persistent Batch restart recovery; Gateway restart recovery remains deferred.

## Non-goals of this PR

- real cross-host PPU/Manager execution adapter
- persistent Batch database/restart recovery
- Mock Profile settings UI
- deterministic Mock profile/seed binding UI
- final operator/user manual
- Render/SWPC 4 MiB memory acceptance
