# Batch Persistence and Gateway Restart Recovery

Status: current server-side Batch durability contract

## Purpose

A server-owned Batch must remain an identifiable execution object when the Web Gateway process restarts. The durability invariant is:

```text
Gateway restart
  -> recover Batch identity and immutable input
  -> reconcile durable Job IDs with authoritative PPU state
  -> never fabricate manufacturing SUCCESS or FAIL from missing Gateway memory
```

Persistence does not make the Gateway the source of truth for physical execution. The PPU remains authoritative for an accepted Job. SQLite preserves the control-plane identity needed to find and reconcile that Job after the observer process restarts.

## Durable boundary

The Gateway persists Batch runtime state in an embedded SQLite database. The current schema version is `1` and uses:

```text
WAL journal mode
synchronous = FULL
foreign_keys = ON
```

The database contains two logical records:

```text
Batch record
  - immutable Batch input/specification
  - frozen Gateway communication policy revision
  - Programming Asset provenance and materialized bytes when present
  - latest Batch/Site execution snapshot
  - terminal flag and timestamps

Batch Job ledger
  - batch_id
  - Facility / PPU / Site
  - operation + round
  - durable job_id
  - submission phase
  - latest authoritative Job snapshot when observed
```

Terminal Batch records are retained for 30 days by default. The schema version is checked at startup; an unsupported schema fails closed instead of silently interpreting incompatible state.

## Submission crash window

A Job ID exists before the Job is submitted to a PPU. The Gateway therefore commits the Job intent before calling the Provider:

```text
allocate job_id
    |
    v
persist phase = submitting
    |
    v
send to PPU
    |
    +-- deterministic rejection -> phase = rejected
    |
    +-- accepted response -> phase = accepted
    |
    +-- timeout / connection loss -> keep phase = submitting
```

`submitting` intentionally means the admission result is ambiguous. The Gateway must not blindly retry the Job after restart because the PPU may already have accepted it.

Recovery queries the PPU by the same durable `job_id`:

```text
PPU reports Job       -> reconcile that Job; do not submit a duplicate
PPU reports NOT_FOUND -> only a durable `submitting` Job may be treated as not accepted
accepted + NOT_FOUND  -> recovery ERROR; do not invent PASS/FAIL
```

This is the idempotency boundary for restart during Job submission.

## Runtime checkpoints and Job ledger

Periodic Batch snapshots preserve operator-visible progress, but they are not sufficient by themselves. A process may crash after the PPU Job reaches a terminal state and before the in-memory Site cursor is advanced.

Recovery therefore rebuilds logical execution counters and the next Site cursor from the durable Job ledger. A terminal Erase/Program/Verify/Read Job cannot be repeated merely because the last memory snapshot was behind the PPU.

The recovered cursor follows the canonical independent-Site execution sequence:

```text
round 1: E -> P -> V -> R
round 2: E -> P -> V -> R
...
```

Only the first operation without durable terminal evidence may be started again.

## Recovery of RUNNING work

On startup, non-terminal durable Batches are reconstructed in memory. For each durable `submitting` or `accepted` Job, the runtime queries the authoritative Provider/PPU status using the frozen Gateway communication policy.

Transient observation failure uses the normal Gateway retry policy. Exhausted communication failure remains infrastructure ERROR; it is not an IC FAIL.

When an observed Job becomes terminal, the Job ledger is updated and Batch execution continues from the rebuilt Site cursor.

## Restart during ABORT

Batch ABORT is idempotent across restart.

If `cancel_requested` / `operator_cancel` was durable before restart, recovery does not resume new manufacturing operations. It reissues cancellation for durable non-terminal Job IDs, observes the authoritative terminal Job state, and only then completes the Batch cancellation state.

A request to cancel is not evidence that a PPU Job already stopped.

## Retained terminal history

A terminal Batch is not required to remain in Gateway RAM. During the retention window:

```text
GET /api/batches/{batch_id}
```

falls back to the retained durable snapshot when the Batch is no longer in memory. Repeated whole-Batch cancel on an already-terminal retained Batch is idempotent and returns the same terminal state.

Private recovery checkpoint fields are not part of the public REST snapshot.

## Programming Asset recovery

When a Batch carries a Programming Asset, the current embedded persistence stores the materialized Asset bytes together with provenance so Program/Verify can re-cache the same immutable Asset after Gateway restart.

This local persistence is a durability mechanism, not a security vault. Authentication, authorization, secret management and at-rest protection are separate security requirements. Remote Write Authentication / Authorization remains an independent control-plane work item.

## PPU execution ownership relationship

Persistent Batch recovery depends on the PPU execution-ownership invariant:

```text
one PPU -> at most one active execution owner
```

The Batch keeps its immutable `batch_id`, so recovered Jobs continue to identify the same logical execution owner. Gateway process lifetime is not the execution-owner identity.

See [PPU Execution Ownership](ppu-execution-ownership.md).

## Independent PPU versus process-coupled Mock

A real/independent PPU may continue executing while the Gateway process is unavailable. The durable runtime can therefore reconcile its accepted Job IDs after the Gateway returns.

The current Engineering Mock topology is different:

```text
Gateway process
   +-- Mock Provider
       +-- in-process Mock PPU servers
```

Restarting the Gateway also destroys those Mock PPU Job registries. There is no independent authoritative Job state left to reconcile. For that topology, a non-terminal Batch recovered after process restart is marked as an infrastructure recovery ERROR with `stop_reason = mock_ppu_restart`.

That result does not mean an IC failed. It states that the simulated PPU execution authority disappeared with the process. Plasma must not fake successful physical recovery from a topology that cannot provide it.

## Retention and schema evolution

Current terminal retention defaults to 30 days. Startup prunes terminal records older than the configured retention period.

Schema version `1` is the initial durable contract. Unknown future schema versions fail closed. Any future migration must be implemented explicitly and covered by migration/recovery tests before deployment.

## Validation requirements

The current recovery regression suite covers at least:

- restart while an accepted Job remains RUNNING;
- ambiguous submission with a durable Job ID;
- transient PPU status failures during recovery retry;
- terminal Job observed before the Site cursor checkpoint advances;
- restart during ABORT with idempotent cancellation;
- accepted Job missing after restart, which fails closed;
- terminal Batch lookup and idempotent cancel after a later restart.

The key invariant in every case is that recovery cannot create a duplicate programming operation or fabricate a manufacturing terminal result from uncertainty.
