# Site Safety Evidence v1

Status: implemented (Host-only). Root cause: 2-Site HIL 2026-11-23, Batch
`1d97a22a`, Site 2 Cycle 15, Job `job-20261123-004025-5406d009`.

## Problem

A C-3 Site Worker `run` that the ABI5 Adapter refused **before any hardware
access** (Root Site admission denied: `PROC_SCAN_INCOMPLETE:PROC_VISIBILITY_DENIED:…:MAPS:ProcessLookupError`)
was judged two ways:

* PPU Runtime (`site_manager._job_safe_off_proven`): safe, by the code prefix
  `TRANSPORT_DENIED:` → Reservation `RELEASE_SAFE_OFF_PROVEN`.
* Manager (`programming._verify`): no `site_worker_result` → `safe_off=None`
  → `SAFE_OFF_NOT_VERIFIED` → Cycle FAIL → `CYCLE_NOT_RELEASED_…`.

Neither side had structured evidence; the PPU trusted a string. The Root
census itself refused because ESRCH on `/proc/<pid>/maps` was not recognised
as a (confirmable) exit — fixed separately in `pl/hil/fpga_image_guard.py`.

## Statement (`plasma.ppu.site-safety.v1`)

Issued only by `ppu_site_worker.SiteWorkerCore.run` (`_safety`) and returned
with the refusal (`{"ok": false, "error": <code>, "safety": {...}}`):

| field | value |
|---|---|
| `schema` | `plasma.ppu.site-safety.v1` |
| `class` | `PRE_HARDWARE_DENIED` (Adapter `TransportDenied`) or `FAILED_SAFE_OFF_VERIFIED` (`TransportFailed`, or an unproven verify-only/read receipt with SAFE_OFF observed) |
| `job_id`, `session_id`, `site`, `operation` | the Worker session's own Job |
| `stage` | `run` |
| `code` | the Adapter code (the refusal is `TRANSPORT_DENIED:`/`OPERATION_FAILED_SAFE:` + `code`) |
| `hardware_touched` | `false` / `true` |
| `safe_off` | `null` (not applicable) / `true` |

No other refusal (lease, `SITE_BUSY`, session, `OUTCOME_UNKNOWN_SITE_SEALED:*`,
unclassified Adapter exceptions) carries a statement. `site_worker_c3`
forwards it as `error.context.site_worker_safety` (never when
`outcome_unknown`).

## Judgment (one shared function)

`plasma_opf.site_safety.site_safety_class` is the one judgment (U9, 2026-11-23);
the PPU Runtime (`plasma_server.site_manager`, Reservation release) and the
Manager (`plasma_manager.programming`, Receipt) both import it. It trusts a
statement only when **all** hold; `tests/test_site_safety_evidence.py` runs one
contract table through both callers:

* `outcome_unknown` is exactly `false`;
* schema, class and a non-empty `code` with `site_worker_code == prefix(class) + code`;
* `site_worker_stage == stage == "run"`;
* statement and context name this Job, Site (int) and operation;
* `PRE_HARDWARE_DENIED`: `hardware_touched is false`, `safe_off is null`;
  `FAILED_SAFE_OFF_VERIFIED`: `hardware_touched is true`, `safe_off is true`.

The Manager additionally requires (`_job_site_safety`): the PPU echoed the
planned Job Binding (sha, Resource Set, Image asset, operations, range, Site,
PPU), Job state `failed|error` equal in Job and result, exactly one attempt,
and Job/Site/operation agreement across Job, result and error. The PPU checks
the Job's own terminal result identity.

## Contract table

| Evidence | Run outcome | Receipt `safe_off` / `safe_off_state` | Cycle | Reservation release | Next step |
|---|---|---|---|---|---|
| Trusted `PRE_HARDWARE_DENIED` | **BLOCKED** `SITE_DENIED_BEFORE_HARDWARE` | `null` / `NOT_TOUCHED` | not settled, not FAIL; attempt archived (`blocked_dispatch` with receipt) | proven | Site pauses (`wait_reason=SITE_DENIED_BEFORE_HARDWARE`, any Cycle, both modes); operator Continue re-runs admission with a new plan/Run/Job; never automatic |
| Trusted `FAILED_SAFE_OFF_VERIFIED` | **FAIL** (`JOB_NOT_SUCCESS`) | `true` / `VERIFIED` | FAIL Cycle | proven | existing FAIL policy (retry if eligible, FAIL_REVIEW) |
| `site_worker_result` with `safe_off: true` | FAIL | `true` / `VERIFIED` | FAIL Cycle | proven | unchanged |
| Code text only, any identity/stage/Binding mismatch, class/code mismatch | FAIL `SAFE_OFF_NOT_VERIFIED` | `null` / `NOT_VERIFIED` | `CYCLE_NOT_RELEASED_SAFE_OFF_NOT_VERIFIED` | **not proven** → `RECOVERY_REQUIRED` | unchanged (conservative) |
| `outcome_unknown` / Site sealed | unchanged | `NOT_VERIFIED` | unchanged | not proven | unchanged; no resend |

Mixed versions fail closed: a new Manager with an old PPU sees no statement
(row 4); an old Manager ignores the extra context field.

## Console

All Logs and views print SAFE_OFF through `batch-statistics.safeOffLabel`
(`VERIFIED` · `N/A · hardware not touched` · `NOT VERIFIED`), separately from
the result. A denied Cycle logs `[BLOCKED] Cycle n/N … denied before hardware
· <code> … not counted as a Cycle · press Start to re-run admission`. Site
`READY` remains the PPU's own Site capability (idle Site + Profile); it is
never derived from a Batch result or a SAFE_OFF label.

## Out of scope

Batch Reservation, Root admission lifecycle, lock protocol and the per-Job
`/proc` census are unchanged. Deduplicating per-Job Root admission against
the Batch Reservation is separate follow-up work.
