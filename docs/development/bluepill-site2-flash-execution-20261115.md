# Site2 Flash execution reconciliation — 2026-11-15

> Historical run 43711950640 report. Superseded by [one-shot Site2 Flash PASS, run 43712609056](../evidence/site2-one-flash-2026-11-15/README.md). CDC mapping is optional observation and is not required to select the SWD Site.

**Physical smoke: NOT_RUN. Previous submission reconciliation: OUTCOME_UNKNOWN. No resend.**

Observed 12:05–12:07 UTC on SWPC, UID 998, Path 3, Runner `plasma-codex`,
run **43711950640**, job `development-codex` (numeric job ID unavailable to
this executor). Candidate PR **#1436**, inspected HEAD
`15ed9ac73167a1e88b419fca08a41cc2d852d203`; trusted dispatcher
`ee8179a3fe8b7cc3a2bd350703b9df8dd3887773`. Owner Work Order digest verified:
`6889d64544daeb210e0b94aafb9e79b5e2af666dbb93fccd9c1588cd5800d0da`.

## Previous attempt

Recovered the private SWPC evidence for run **43711477559**, job
**132803809186**, comment **6893964078**. All ten recorded SHA256SUMS match.
Its acceptance record SHA256 is
`74fe6752b85646dea222885328aebee65899bf80f814b48ab55e66fc352ddaaf`.
It records `hardware_flash: NOT_RUN`, zero attempts, no receipts, and
`execute_command: NOT_RUN: verified --port unavailable`. Its blocker was
`SITE2_CDC_PHYSICAL_ASSOCIATION_NOT_VERIFIED`.

Thus the recovered record reports **(b) no submission**, not **(a) a verified
Flash**. Independent verification of whether that attempt made any POST remains
**(c) OUTCOME_UNKNOWN**: neither its record nor current accessible interfaces
provides a complete request/journal history. Absence of receipts is not proof
of absence of submission. Its GitHub SUCCESS / `EVIDENCE_READY_REVIEW_REQUIRED`
and `functional_acceptance: UNVERIFIED` are not hardware acceptance.

The recovered `POST /api/registry/z2/bootstrap/programming/plans` HTTP **409**
belongs to the earlier run **43709392830**, not 43711477559. It records a null
preview plan ID and unpaired state. No Start, Batch, or Run ID was recovered
for either attempt; no new IDs were issued in this continuation.

## Current observations and executable blockers

Read-only commands used the loopback Manager, without authentication material
in arguments or output:

| Command / observation | Observed result |
| --- | --- |
| `GET /api/fleet` | HTTP 200; current, non-stale Z2 observation; ready; no active owner or Jobs |
| `GET /api/registry/z2/bootstrap` | HTTP 200; paired, device match/authenticated; controller generation 2, NORMAL; enrollment EXPIRED |
| `GET /api/ppus/z2/gateway/api/status` | HTTP 200; Site2 idle, queue 0, no current Job |
| `GET /api/programming/starts`, `/api/programming/batches`, `/api/programming/runs` | HTTP 404; no list history available |
| `GET /api/registry/z2/bootstrap/programming/runs` | HTTP 404, `bootstrap_route_not_allowed` |
| Managed GET of the known Job detail | HTTP 404, `managed_route_not_allowed` |
| Local Manager configuration/state directory inspection | `PermissionError`, errno 13 under current UID |
| `journalctl` for the prior attempt window | No journal files opened: insufficient permissions |

Site2 latest Job remains **`job-20261115-030715-47406b07`**, reported success
at **03:07:21.956450 UTC**, already present before 43711477559. It is not a
receipt for either continuation. Its Start/Batch/Run IDs and physical readback
are unavailable through the inspected interfaces. Current idle state cannot
reconcile historical submission outcomes.

CDC identities **8D8C067A5749** (`ttyACM0`) and **4997124A3133** (`ttyACM1`)
are both currently present and readable/writable. Their physical association
to Site2 SWD is **NOT_VERIFIED**, so no verified `--port` can be selected.
Recovered earlier CDC observations show respectively version **0.1** with
500 ms heartbeat increments and version **0.2** with 1000 ms increments.
These are historical observations, not current Site2 identity/heartbeat PASS.
No ambiguous CDC device was probed in this continuation.

## Images and disposition

Existing fixture archive payloads were rehashed locally:

| Image | Bytes | SHA256 |
| --- | ---: | --- |
| v0.1 | 18768 | `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d` |
| v0.2 | 62800 | `e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c` |

This continuation made **zero POSTs and zero Flash attempts**. The existing
`plasma_engineering_hil.py --execute` A/B/A smoke was **NOT_RUN**, as required
by the Work Order's no-blind-resend condition. Three receipts, readback SHA,
SAFE_OFF, current CDC version/heartbeat, electrical/Root safety and current
resource reuse are **NOT_VERIFIED**. No FPGA load, deployment, restart,
other-Site operation, recovery, or merge occurred.

Next minimal correction: obtain a credential-safe, read-only Manager journal
and request-history reconciliation using an already authorized identity with
access, and establish the physical Site2 SWD-to-CDC serial mapping. Only proven
non-submission plus the remaining current safety checks permits the original
smoke; any admitted attempt must first be reconciled. No new approval gate is
asserted here.

Private evidence retained with checksum manifest under the existing Path 3
engineering evidence collection: current HTTP responses, prior acceptance
records, image checks and access errors. Only this report is a publishable
worktree change. The existing trusted publisher must verify the unchanged
authorized PR HEAD before commit/push; publication is pending that post-Codex
step. Report validation: prior checksums and both image hashes PASS; hardware
acceptance NOT_RUN. Gate 2 merge approval has not been requested or granted.
