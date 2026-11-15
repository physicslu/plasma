# SWPC Control Station — Path 2 fixed CLI adapter (Gate 1)

**Status:** Draft PR #1443; Host-only implementation. SWPC Path 2
execution, Control Station deployment and hardware HIL are **NOT_RUN**.

## Responsibility boundary

- **Path 3:** diagnose, fix, test, and review implementation changes.
- **Path 2:** issue owner-approved, source-pinned, deterministic
  `status`, `verify` or `deploy` commands with a real execution receipt.
- The existing Issue #981 Dispatcher and non-root Runner are reused.
  No new Runner, privileged installer, generic shell bridge or sudoers edit.

The existing canonical Control Station backend is a Bash script and
the existing Path 2 `operator-cli` admits a reviewed Python `.py` entrypoint.
`scripts/plasma_path2_control_station.py` is the narrowly bounded adapter.
It never executes the UID 998 Runner's private checkout as UID 1000.
Instead it invokes the existing fixed operator-owned checkout, under the
existing operator user-systemd account and only if actual OS permissions
permit. Failure to cross this boundary is BLOCKED, not PASS.

## Independent source identities

**These are two distinct source identities, not one SHA:**

1. **Adapter source SHA:** the exact owner-approved PR #1443 HEAD, bound
   by the trusted Path 2 Dispatcher and validated in the Runner checkout.
   This controls which Python adapter is permitted to execute.
2. **Target source SHA:** the separately reviewed Control Station candidate
   (e.g. PR #1435 HEAD), passed as `--target-sha` in the immutable
   owner Work Order for `deploy` only. The adapter checks the operator-owned
   checkout's exact HEAD and clean tracked state, and checks the immutable
   target Git objects contain both the Preflight script and canonical
   deployment function with its two Preflight checkpoints.

No unreviewed candidate checkout may be inferred from a branch name.
Read-only `status` and `verify` need only the Adapter SHA and report the
actual operator checkout separately; `--target-sha` and maintenance flags
are rejected for those two operations. All execution is one-shot. A nonzero
exit, missing permission, invalid provenance, or timeout must be recorded
without automatic retry.

## Safe sequence and current blocker

1. PR #1435 recorded **six legacy CONSUMED Starts** with live Manager
   `JOURNAL_INCONSISTENT`. Preserve all originals and prove their identity;
   never delete the journal or auto-acknowledge unknown transactions.
   PR #1444 proposes a narrowly scoped, read-only legacy compatibility
   rule and separate negative regressions. This is not deployed.
2. Independently establish operational maintenance exclusivity and
   suspension of new Manager admission. Two Preflight snapshots and the
   `--owner-maintenance-confirmed` flag are **not** a lock. Without that
   evidence, do **not** dispatch `deploy`.
3. Verify the current installed SHA, rollback pin, Manager/Console health,
   Start/Run/Batch journals, and PPU execution ownership via read-only
   commands.
4. Only after (1) and (2) are genuinely satisfied, use a source-pinned
   Path 2 Work Order with both SHAs to request a single deploy.
   The canonical backend must check Preflight before release creation
   and immediately before activation.
5. Re-run independent `verify`; preserve actual Run ID, Job ID, exit code,
   current/previous release SHAs and safe rollback evidence.

**Do not deploy solely because this adapter passes CI.** No PPU Runtime,
FPGA or DUT action is implicit in Control Station deployment. PR #1436
Blue Pill smoke/burn-in requires separate physical qualification.

## Work Order template (read-only qualification)

Use the existing owner-only Issue #981 work-order path. Replace the SHA
placeholder with the then-current exact PR #1443 HEAD:

```json
{
  "schema": "plasma.development.work_order.v1",
  "execution_path": "path2-cli",
  "capability": "operator-cli",
  "scope": "guarded-hardware",
  "pr_number": 1443,
  "source_sha": "<ADAPTER_SHA_40_HEX>",
  "script": "scripts/plasma_path2_control_station.py",
  "argv": ["status", "--source-sha", "<ADAPTER_SHA_40_HEX>"],
  "timeout_seconds": 120,
  "monitor_summary": "SWPC Control Station read only status",
  "objective": "Read-only inspection of the operator-owned Control Station.",
  "acceptance": "Observed Runner, Run/Job, source and installed release; no mutation."
}
```

For a separately owner-reviewed **future** deploy, change only the
bounded argument list and Work Order objective/acceptance after safety
prerequisites are proven:

```json
["deploy", "--source-sha", "<ADAPTER_SHA_40_HEX>",
 "--target-sha", "<CONTROL_STATION_SHA_40_HEX>",
 "--owner-maintenance-confirmed"]
```

The source SHA and target SHA serve different trust boundaries. The
Dispatcher validates the adapter PR; the operator-owned checkout must
match the target SHA. A status query is **not** deployment admission.

## Host-only qualification

Positive/negative tests cover source SHA, dirty checkouts, wrong host,
invalid or missing target SHA, missing Git objects, missing dual
preflight, fixed owner invocation, unauthorized operations and flags,
nonzero exit, unknown timeout and one-shot semantics.

GitHub-hosted tests are **not** evidence of actual SWPC permission,
user-systemd behavior, release activation, rollback, Z2 or DUT.
