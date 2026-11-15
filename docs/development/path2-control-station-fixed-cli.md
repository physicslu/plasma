# SWPC local Control Station — fixed Path 2 execution (Gate 1)

Status: **Draft/Host-only; not deployed; no SWPC Job or HIL qualification.**

## Decision and boundaries

Use Path 3 only for autonomous diagnosis, code changes, and fix/retest. Use the
existing owner-only Issue #981 Path 2 `operator-cli` route for the bounded
`local-control-station` status / verify / deploy operations. Do **not**
change global Dispatcher concurrency, add a Runner, introduce a shell/SSH
gateway, or grant new sudoers privileges in this change.

The Dispatcher accepts a repository-relative Python script as its fixed
entrypoint. `scripts/plasma_path2_control_station.py` is that bounded adapter.
It accepts only `status`, `verify`, `deploy`, and a 40-hex exact Git SHA;
it checks Linux host `swpc`, clean pinned checkout, and the single canonical
Bash backend. It invokes only the fixed operator-owned backend
the fixed operator checkout's canonical Control Station backend once,
without `shell=True` or retry, under existing the operator account ownership using
`sudo -n -H -u operator`. It never asks UID 1000 to execute a Bash script
from UID 998's private Runner candidate checkout. It supplies UID 1000's
user-systemd runtime environment. `deploy` additionally checks the
operator checkout's clean HEAD exactly matches the authorized Path 2 PR
source SHA; if the required combined PR #1435 + #1443 source has not been
safely staged for the operator account, deployment is BLOCKED, not silently performed
from a different release. Read-only `status` and `verify` use the existing
operator checkout and must report its observed source separately from the
adapter PR source. If delegation or fixed owner checkout is unavailable,
record BLOCKED/NOT_RUN, never call it a successful deploy.

A Path 2 Runner is UID 998 and is **not** implicitly the user-systemd owner.
The existing developer sudo delegation, if present, remains operator-managed
and is not installed, modified or broadened by this PR.

## Dependency and safe sequence

1. Resolve the six legacy consumed Starts that the Manager currently reports
   `JOURNAL_INCONSISTENT`; preserve the real Start/Run/Batch journals.
   PR #1435's preflight appropriately BLOCKED on this evidence.
2. Confirm operational maintenance exclusivity, including no new Manager Batch
   admission, via actual independent controls. A human assertion flag is **not**
   a Manager admission lock and two idle preflight snapshots are **not**
   an atomic quiesce barrier.
3. Select the exact, owner-reviewed PR SHA containing **both** this adapter
   and PR #1435's `run_deployment_preflight` checks. The original main
   Control Station deployment backend without #1435 must fail closed.
4. Run fixed `status` and `verify` first, capturing Run/Job/exit and
   active release SHA, configured PPU alias and service state.
5. Only with proved transaction reconciliation and exclusive maintenance,
   run one source-pinned `deploy` using `--owner-maintenance-confirmed`.
   The canonical backend performs preflight *before build* and *before
   activation*. A failure or unknown timeout is not automatically retried.
6. After real deploy exit 0, independently run fixed `verify`, preserving
   deployed SHA, original rollback pin, Manager/Console health and PPU
   owner status. Do not infer DUT readiness or electrical/HIL evidence.

`--owner-maintenance-confirmed` is **only** an explicit owner intent guard:
it cannot substantiate item 2. If item 2 is not independently demonstrated,
**do not dispatch deploy** even if that flag could be supplied.

## Path 2 Work Order shape

Submit only through the existing Owner issue-comment Dispatcher and with
the exact **then-current** adapter-branch SHA, not a mutable branch name.
The JSON object below illustrates a read-only qualification, not a ready-made
authorized deployment. Replace `<HEAD_SHA_40_HEX>` with actual commit SHA
and supply the approved Objective and Acceptance before submission.

```json
{
  "schema": "plasma.development.work_order.v1",
  "execution_path": "path2-cli",
  "capability": "operator-cli",
  "scope": "guarded-hardware",
  "pr_number": 1443,
  "source_sha": "<HEAD_SHA_40_HEX>",
  "script": "scripts/plasma_path2_control_station.py",
  "argv": ["status", "--source-sha", "<HEAD_SHA_40_HEX>"],
  "timeout_seconds": 120,
  "monitor_summary": "SWPC local Control Station read-only status",
  "objective": "Read only, verify pinned operator-owned Control Station state.",
  "acceptance": "Report actual Run/Job, exit code, installed release and no mutation."
}
```

**Important:** the example is bound to Draft PR #1443 and must use the
**actual current PR HEAD** in both SHA positions. Once merged to trusted main,
a new Work Order with `pr_number: 0` must instead use the current main SHA.
The Dispatcher does not accept a branch with a different arbitrary SHA.

For a separately authorized later deploy, replace the fixed `argv` by
`["deploy","--source-sha","<HEAD_SHA_40_HEX>","--owner-maintenance-confirmed"]`
**only** after the above admission/maintenance prerequisites have been
verified. Stop if any state is unknown. No Z2 Runtime/FPGA/DUT action is
authorized by this adapter. #1436 HIL remains a separate work order.

## Qualification

Host-only unit tests check the bounded operation, exact SHA, wrong host,
dirty source, operator-checkout SHA / dirty-source rejection, fixed owner command,
required dual preflight hooks,
maintenance intent guard, nonzero command result and timeout with no retry.

A green hosted Python CI proves only the adapter's host-only contract.
Only real SWPC Path 2 Run+Job evidence proves that UID 998 can execute
the fixed operator-owned command, and only the actual canonical CLI
preflight + service verification can qualify the candidate deployment.
