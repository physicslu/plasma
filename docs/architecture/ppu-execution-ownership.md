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
3. Legacy/direct Protocol Jobs fall back to their logical `client_id`.

The explicit owner fields must be supplied as a pair. Partial owner metadata is invalid.

Examples:

```text
Batch A / SITE-01  ----+
Batch A / SITE-02  ----+--> allowed: same PPU owner

Batch B / SITE-03  --------> rejected while Batch A owns the PPU

Client X / SITE-01 ----+
Client X / SITE-02 ----+--> allowed for one logical client owner

Client Y / SITE-03 --------> rejected while Client X owns the PPU
```

## Lease lifecycle

The first accepted Job for an idle PPU acquires the lease before the Job is entered into the registry/worker queue. Additional Jobs from the same owner are added to the lease.

Every accepted Job registers a terminal callback. When a Job becomes terminal it is removed from the lease. The lease is released when the last owned Job becomes terminal. Cancellation follows the same rule: requesting cancellation does not release ownership; terminal Job state does.

This prevents another owner from entering while the original owner's work is still running or queued.

## Conflict contract

A conflicting submission is rejected before Job creation with the stable Plasma error:

```text
E4010 PPU_BUSY
```

The error is recoverable and includes the active/requested owner identity in structured context for diagnostics. A PPU-level STATUS snapshot exposes only operational ownership state:

```text
execution.busy
execution.owner_kind
execution.owner_id
execution.active_job_count
```

The ownership state is execution/control-plane state. It is not a manufacturing PASS/FAIL result.

## Batch behavior

All Jobs created by one server-side Batch already carry `batch_id` metadata. This makes PMode and EMode server-side Batch Jobs share one PPU owner even when they run concurrently across multiple Sites.

Two different Batch IDs cannot execute on the same PPU at the same time, even though both use the common `plasma-batch-runtime` client identity.

## Scope and limitations

This PR establishes the non-overlap invariant at the PPU execution boundary. It does not persist leases across a Plasma Server process restart; restart reconciliation belongs to the separate Persistent Batch State / Gateway Restart Recovery work.

Authentication and authorization are also separate. Execution ownership prevents accidental/concurrent control-plane overlap; it is not an identity security mechanism. Remote write authentication is required before treating owner identity as a security principal.

The current lease is tied to active Jobs. A Batch may have short orchestration gaps between terminal Jobs and its next Job submission. Cross-PPU all-or-nothing reservation for an entire Batch is not claimed by this contract; the safety invariant guaranteed here is that two different owners never have active Jobs on the same PPU simultaneously.