# PPU Execution Ownership

## Purpose

A physical PPU is one execution resource even when it exposes multiple independent Programming Sites. Plasma therefore enforces this backend invariant:

```text
one PPU -> at most one active execution owner
```

The invariant is enforced at the Plasma Server / `SiteManager` boundary rather than only in React or the Web Gateway. A UI guard is useful for operator experience, but it is not an execution safety boundary because a future Plasma Manager, another browser, CLI, or direct Plasma Protocol client may reach the same PPU through another path.

## Owner model

One logical owner may run multiple Site Jobs concurrently on the same PPU. A different owner is rejected while any Job belonging to the active owner remains non-terminal.

Owner resolution is deterministic:

1. Explicit `execution_owner_kind` + `execution_owner_id` metadata, when both are supplied.
2. A server-side Batch uses its immutable `batch_id` as owner identity.
3. Web `startJob()` supplies one page-instance execution-owner ID so concurrent direct Site Jobs from one Browser page can share the PPU while a different page/PC receives a different owner identity.
4. Unscoped raw Web REST Jobs whose process-global client label is `plasma-web` or `plasma-web-engineering` fail closed to one `rest_job` owner per Job ID. A fixed Gateway client label is not treated as proof that two requests came from the same operator/client.
5. Other direct Plasma Protocol Jobs fall back to their explicitly supplied logical `client_id`.

The explicit owner fields must be supplied as a pair. Partial owner metadata is invalid.

Examples:

```text
Batch A / SITE-01  ----+
Batch A / SITE-02  ----+--> allowed: same PPU owner

Batch B / SITE-03  --------> rejected while Batch A owns the PPU

Browser Page A / SITE-01 ----+
Browser Page A / SITE-02 ----+--> allowed: same page-instance owner

Browser Page B / SITE-03 --------> rejected while Page A owns the PPU

Protocol Client X / SITE-01 ----+
Protocol Client X / SITE-02 ----+--> allowed for one explicit logical client owner

Protocol Client Y / SITE-03 --------> rejected while Client X owns the PPU

Unscoped raw REST Job A ------------> owns PPU as rest_job:A
Unscoped raw REST Job B ------------> rejected until A is terminal
```

The Browser page-instance owner is intentionally an execution/concurrency label, not a security principal. It exists so the current direct multi-Site Web workflow can express one logical owner without trusting the process-global Gateway `client_id`. A page reload creates a new owner; if previous Jobs are still active, the new page must wait for their authoritative terminal state rather than silently taking ownership.

Until Remote Write Authentication / Authorization supplies a trustworthy principal identity, the backend must not treat a client-supplied owner token as authorization. Raw REST requests that omit an explicit owner continue to fail closed per Job. Server-side PMode/EMode Batch execution uses immutable `batch_id` and does not depend on the Browser token.

## Admission and lease lifecycle

Admission is deliberately ordered to protect duplicate Job IDs:

1. validate the request and Site;
2. create the new `JobRuntime` in `JobRegistry`, which fails immediately on a duplicate `job_id`;
3. acquire or join the PPU execution lease;
4. persist initial Job state and dispatch to the Site worker.

Registry creation is not PPU execution. Lease acquisition still happens before any worker dispatch. This ordering means a duplicate `job_id` cannot mutate or release the existing Job's lease during rollback.

The first admitted Job for an idle PPU acquires the lease. Additional Jobs from the same owner are added to the lease. If lease admission or worker preparation fails after creation of the new registry record, only that newly created record is discarded and its lease membership is rolled back.

Every accepted Job registers a terminal callback. When a Job becomes terminal it is removed from the lease. The lease is released when the last owned Job becomes terminal. Cancellation follows the same rule: requesting cancellation does not release ownership; terminal Job state does.

This prevents another owner from entering while the original owner's work is submitting, queued, running or cancelling.

Browser or network loss does not release the lease. Ownership is tied to authoritative PPU Job lifecycle rather than a browser connection, so a disconnected client cannot cause valid PPU work to be silently re-owned.

## Conflict contract

A conflicting submission is rejected before worker dispatch with the stable Plasma error:

```text
E4010 PPU_BUSY
```

The error is recoverable and includes the active/requested owner identity in structured context for diagnostics. A PPU-level STATUS snapshot exposes operational ownership state:

```text
execution.busy
execution.owner_kind
execution.owner_id
execution.active_job_count
```

The ownership state is execution/control-plane state. It is not a manufacturing PASS/FAIL result.

The canonical REST surface preserves `PPU_BUSY` as an explicit admission conflict:

```text
HTTP 409 Conflict
E4010 PPU_BUSY
```

The PPU protocol error remains authoritative; HTTP 409 is its Web REST representation.

## Batch behavior

All Jobs created by one server-side Batch already carry `batch_id` metadata. This makes PMode and EMode server-side Batch Jobs share one PPU owner even when they run concurrently across multiple Sites.

Two different Batch IDs cannot have active Jobs on the same PPU at the same time, even though both use the common `plasma-batch-runtime` client identity.

The legacy/direct Browser multi-Site workflow does not create server-side Batch records. Its calls therefore carry the page-instance owner ID generated by `plasma-api.ts`, allowing its parallel Site Jobs to share one execution owner without weakening raw REST fail-closed behavior.

## Scope and limitations

This change establishes the active-work non-overlap invariant at the PPU execution boundary. It does not persist leases across a Plasma Server process restart; restart reconciliation belongs to the separate Persistent Batch State / Gateway Restart Recovery work.

Authentication and authorization are also separate. Execution ownership prevents accidental/concurrent control-plane overlap; it is not an identity security mechanism. Remote write authentication is required before treating owner identity as a security principal.

The current lease is tied to active Jobs. A Batch may have short orchestration gaps between terminal Jobs and its next Job submission. Cross-PPU all-or-nothing reservation for an entire Batch is not claimed by this contract; the guaranteed invariant is that two different owners never have submitting, queued, running or cancelling Jobs on the same PPU simultaneously.
