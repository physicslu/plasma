# Programming Start Outcome Reconciliation v1

Status: Gate 1, Host-only. Not deployed, no HIL. Manager + Console only; the
PPU Gateway, Runtime, C-3 and FPGA are unchanged.

## Problem

A Console Start (`POST programming/runs`, `POST programming/batches`) can lose
its HTTP answer. The Manager may or may not have admitted it. Before this
contract the Console had no identity to ask about, so its only release check
was "the Site is idle with no Job", which proves nothing about the lost Start.

## Start identity

Every Start carries a **Manager-issued `start_id`** (32 hex):

| Start | `start_id` | Issued by |
|---|---|---|
| run (READ, single programming run) | the plan's `plan_id` | `POST programming/plans` (existing) |
| EMode Batch | a start ID | `POST programming/starts` `{"kind":"batch"}` (new) |

The Console therefore holds the identity **before** the Start request leaves.
A Batch request carries it as `start_id`; a `start_id` admits at most one
Batch, and an unknown, used, voided or expired one is refused
(`409 programming_start_not_startable`). A Batch without `start_id` behaves as
before.

## Journal

No second ledger. The existing run journal (`bundle-programming-runs.json`)
gains one additive key, `starts`: one admission record per issued `start_id`
(`kind`, `ppu_alias`, `site_id`, `ppu_id`, `operation`, `job_binding_sha256`,
`state`, `run_id` / `batch_id`). The Batch journal record gains `start_id`.

| Step | Written (fsync + atomic replace) before |
|---|---|
| issue (`plan`, `starts`) | record `ISSUED` before the ID is returned |
| run admission | run + record `CONSUMED` in ONE journal write, before the run is spawned and before the answer is sent |
| Batch admission | record `CONSUMED` first, then the Batch record, then spawn, then the answer |
| void | record `VOIDED` |

Startable plans and Batch start IDs live in memory only (as plans always did):
a Manager restart ends them. A journal write failure at admission spawns
nothing and keeps no run / Batch in memory.

An older Manager ignores `starts` and drops it on its next write; the IDs it
dropped then reconcile to `OUTCOME_UNKNOWN`, never to "not accepted".

## API

All under `/api/registry/{alias}/bootstrap/programming/` (Browser: same path
under `/api/manager/registry/...` through the BFF allowlist).

| Method | Path | Effect |
|---|---|---|
| `POST` | `starts` | Issue a Batch start ID. Submits nothing. |
| `GET` | `starts/{start_id}` | **Reconciliation. Read-only.** |
| `POST` | `starts/{start_id}/void` `{"void":"VOID_UNSTARTED_START"}` | Operator: drop an unconsumed plan / start ID. Refuses an admitted start (`409 programming_start_not_voidable`). |

`GET starts/{start_id}` reads the journal and memory only. It never contacts a
PPU, never submits, retries, acknowledges or writes the journal; repeating it
changes nothing. It answers `200` with:

```json
{"ok": true, "reconciliation": {
  "schema": "plasma.manager.programming-start-reconciliation.v1",
  "start_id": "…", "ppu_alias": "z2", "kind": "run|batch|null",
  "state": "…", "reason": "…", "outcome": "PASS|FAIL|BLOCKED|STOPPED|OUTCOME_UNKNOWN|null",
  "identity": {"ppu_alias", "site_id", "ppu_id", "operation", "operations", "job_binding_sha256"},
  "run": {…}, "batch": {…},
  "acknowledged": false, "unknown_run_id": "…", "expires_in_s": 1800,
  "read_only": true, "auto_retry": "DISABLED"}}
```

## States

| `state` | Evidence required | Console |
|---|---|---|
| `NOT_ACCEPTED` | journalled record `VOIDED`, or `ISSUED` and no longer admissible (plan / start ID gone from memory or expired) and no run / Batch carries the ID | hold may be released |
| `ACCEPTANCE_PENDING` | record `ISSUED` and the Manager still holds a startable plan / start ID: a delayed request could still be admitted | hold kept; operator may void |
| `ACCEPTED_RUNNING` | run / Batch with this ID, no outcome yet | hold kept |
| `TERMINAL_CONFIRMED` | run `PASS` / `FAIL` / `BLOCKED`, Batch also `STOPPED` | hold may be released |
| `OUTCOME_UNKNOWN` | the run / Batch is `OUTCOME_UNKNOWN`, or nothing can be proven | see below |

`OUTCOME_UNKNOWN` reasons that are not a run's own reason:
`START_NOT_RECORDED` (no record: journal lost, rolled back, record dropped by
retention), `ADMITTED_RECORD_MISSING` (record `CONSUMED`, run / Batch gone),
`JOURNAL_INCONSISTENT` (record and run / Batch disagree on kind, state, ID,
Site or Job Binding SHA256), `START_IDENTITY_MISMATCH` (the ID belongs to
another PPU; nothing about it is returned).

A deleted plan and an idle Site are never evidence. `NOT_ACCEPTED` always
rests on a journalled, never-consumed issue record.

An unreadable journal still refuses to start the workflow (unchanged).

## Console (EMode)

`localStorage` (`plasma.emode.start-outcome-unknown.v1`) keeps only what is
needed to ask again after a reload: alias, Site, kind, `startId`,
`jobBindingSha256`. It is never the authority.

Operator button **Reconcile Start with Manager** → `GET starts/{id}` →
`decideStartReconciliation`:

1. The answer must be for this `start_id` and PPU, and its identity must match
   the held Site, Operation, kind and (for a run) Job Binding SHA256. Otherwise
   the hold is kept.
2. `NOT_ACCEPTED`, `TERMINAL_CONFIRMED`, or `OUTCOME_UNKNOWN` whose run is
   already acknowledged on the Manager → release, and only if the Manager Fleet
   also shows the Site enabled, idle, with no Job (the previous policy, now an
   additional condition instead of the only one).
3. `OUTCOME_UNKNOWN` with an unacknowledged run → a second explicit button,
   **Acknowledge Run reconciliation**, sends the existing
   `runs/{run_id}/acknowledge`. Never automatic.
4. `ACCEPTANCE_PENDING` → a second explicit button, **Void the unstarted
   Start**. Never automatic.
5. Anything else, a failed request, or a hold without `startId` → hold kept,
   reason shown and logged.

The hold blocks READ and START for the whole PPU, survives a reload, reaches
other tabs through the `storage` event, and is independent of the selected IC,
Site, Source or Operations.

## Known limits

- A hold whose Start the Manager cannot prove anything about
  (`START_NOT_RECORDED`, `ADMITTED_RECORD_MISSING`, `JOURNAL_INCONSISTENT`,
  mismatch, or no `startId`) cannot be released from the Console. There is no
  override in this version.
- The hold is per Browser profile. Another Browser is stopped only by the
  Manager's own guards (one active run per PPU, the OUTCOME_UNKNOWN latch).
- The result of a reconciled READ is not delivered: the operator reads again.
- PMode (`runManagedProgramming`) carries the start identity in its error but
  has no hold UI in this version.
- Record retention is 256 start records; a dropped record reconciles to
  `OUTCOME_UNKNOWN`.
