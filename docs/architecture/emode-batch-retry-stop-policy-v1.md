# EMode Batch Retry / Stop Policy v1 — Manager-owned coordinator

Status: implemented Host-only (Gate 1, 2026-11-11). No hardware evidence. Depends on
[OPF Programming Operations v1](opf-programming-operations-v1.md).

## Scope

One Batch = one PPU, one Site, one programming Job specification (an ordered erase / program /
verify `operations` list with its Programming Image, Bundle or erase range) and a policy
`{repeat: 1, retry_limit, stop_policy}`.

* **Repeat is not implemented.** `repeat` must be 1; anything else is `400 repeat_not_supported`.
  There is no Repeat scheduler, IC / cycle model or fixture exchange here.
* Read Memory is never part of a Batch.
* This is not the PMode durable multi-PPU production scheduler and not a Gateway batch runtime.
  The coordinator (`plasma_manager/programming_batch.py`) only decides whether **another attempt
  is submitted**; every attempt is an ordinary Manager plan + run.

## Attempts

Every attempt is a new plan, a new run and a new PPU Job (new Job ID; `auto_retry = DISABLED`,
exactly one submission). The Job Binding is re-derived by the Manager and re-verified by the PPU
for each Job; its SHA256 is a content identity and is the same for an identical Job
specification on the same PPU and Site. The attempt journal records plan ID, run ID, Job ID,
Binding SHA256, outcome, reason, SAFE_OFF and the retry decision, and is written **before** each
submission.

## Retry

| Attempt outcome | Next step |
| --- | --- |
| `PASS` | Batch `PASS` |
| `OUTCOME_UNKNOWN` (lost submission, timeout, HTTP 5xx, disconnected, incomplete evidence, Manager restart) | Batch `OUTCOME_UNKNOWN`. **Never retried**, no retry budget is consumed, the workflow latch stays until an operator reconciles and acknowledges |
| `BLOCKED` (nothing submitted) | Batch `BLOCKED` |
| `FAIL` | retried only if **all** conditions below hold and the policy allows it |

A `FAIL` is retry-eligible only when:

1. the run has a receipt of exactly one submitted Job in a terminal state;
2. SAFE_OFF is verified in that receipt;
3. the PPU echoed the planned Job Binding and Resource Set;
4. the PPU reads as released: reachable, Site idle with no Job, no held execution lease, no
   active or unknown run, no `RECOVERY_REQUIRED` (a SEALED Site never reports SAFE_OFF verified
   or idle readiness, so it is never eligible).

An HTTP 4xx rejection, a missing receipt or any unreadable state is **not** a retryable FAIL.
`retry_limit` is 0–5 (`MAX_RETRY_LIMIT`).

## Stop Policy

Controls only attempts that are not submitted yet.

* `{"kind": "never"}`
* `{"kind": "failed_sites", "threshold": 1..N}` — once that many Sites have failed, nothing
  further is submitted, even with retries left. N is the Batch's own Site count (PR-C; before it
  a Batch had one Site and 1 was the only threshold).
* `POST /api/programming/batches/<id>/stop` with `{"stop": "STOP_QUEUING"}` — the Console's
  **STOP QUEUING** button. It never cancels a submitted Job, releases a Site lease, cancels an
  unknown run, resets a PPU or clears recovery state; the running attempt is observed to its
  real end. There is no cancel / abort route.

## Outcomes and counting

Batch outcome: `PASS`, `FAIL`, `PARTIAL`, `OUTCOME_UNKNOWN`, `BLOCKED`. Worst wins
(`OUTCOME_UNKNOWN > FAIL > PARTIAL > PASS`). **One Site is one IC**, counted once by that Site's
own final outcome (`counts.pass` / `counts.fail` / `counts.blocked` / `counts.unknown` over
`counts.sites`); failed attempts that were retried are not FAIL ICs. Before PR-C a Batch was one
Site, so the Batch outcome and the Site outcome were the same thing; they are not any more.

## Restart

Nothing is resubmitted after a Manager restart. An interrupted Batch is closed from the journals:
`BLOCKED` (`MANAGER_RESTARTED_BEFORE_SUBMISSION`) when its last attempt had provably not been
started, the attempt's own outcome when the run had finished, otherwise `OUTCOME_UNKNOWN`
(`MANAGER_RESTARTED_DURING_ATTEMPT`), which stays latched. An unreadable journal refuses to start.

## API

`POST /api/programming/batches` (202), `GET /api/programming/batches/<id>`,
`POST /api/programming/batches/<id>/stop`. The Batch is Manager-owned, so none of these sits
under a PPU alias; the alias-scoped entry retired in PR-C (architecture contract §5.8).
A Batch is refused up front (no Batch, no plan) while another Batch or run is in progress or an
`OUTCOME_UNKNOWN` run is unacknowledged on that PPU.
