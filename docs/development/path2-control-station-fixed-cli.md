# SWPC Control Station — fixed Path 2 owner CLI adapter (Gate 1)

**Status:** Draft PR #1443, Host-only. No SWPC execution, live deployment
or HIL qualification. **Current adapter allows read-only status/verify only.**

## Responsibility and privilege boundary

Path 3 performs autonomous diagnosis, source changes and fix/retest.
Path 2 performs deterministic, source-pinned operations through the
existing Issue #981 Dispatcher and SWPC non-root Runner.

The Path 2 Dispatcher admits reviewed Python entrypoints, not arbitrary
Bash commands. `scripts/plasma_path2_control_station.py` is a fixed Python
adapter. It verifies its own exact 40-character source HEAD and clean
checkout before a one-shot execution of the independently installed
fixed Control Station owner bridge:

```text
/usr/local/libexec/plasma/plasma-control-station-owner-bridge
```

The sole privileged operation issued by the adapter is `sudo -n -H -u
<operator-role> -- <installed-fixed-bridge> status|verify`. It does
**not** execute sudo Bash, Git, Python, env, systemctl, arbitrary
commands or shell under UID 1000. The bridge is a distinct root-owned,
immutable, trusted-administrator-installed program governed by
Draft PR #1429. The Runner cannot install the bridge or edit sudoers.

No evidence yet proves this bridge is installed or that its exact-argv
sudoers allowance exists. An unavailable or denied bridge is explicitly
BLOCKED / NOT_RUN, not a successful check. Only actual run receipts can
demonstrate SWPC owner-service access.

## Deploy remains fail-closed

The `deploy` word remains an explicit CLI choice only to return a
predictable `DEPLOY_BRIDGE_NOT_QUALIFIED` refusal. Supplying a
`--target-sha` or `--owner-maintenance-confirmed` flag does **not**
enable deployment. These flags are rejected with read-only operations.

Future deployment will need an independently reviewed fixed-command
Bridge upgrade with two distinct source identities:

1. Adapter source SHA — the trusted Path 2 Dispatcher-pinned PR HEAD.
2. Target release SHA — the independently reviewed immutable Control
   Station source, including PR #1435 double Preflight and any required
   Manager legacy Start reconciliation.

Do **not** combine these SHAs or infer identity from mutable branch names.

Current blockers include six live `CONSUMED Start` responses of
`JOURNAL_INCONSISTENT` on the existing Manager, no proof of atomic
maintenance/no-new-admission exclusivity, and a version transition
deadlock because PR #1444's compatibility exists only in the NEW
Manager. Neither a manual maintenance flag nor two idle snapshots
establish exclusivity. No journal rewrite, automatic UNKNOWN
acknowledgement, unreviewed sudoers change or forced restart is allowed.

## Owner Work Order shape — read-only example only

An authenticated owner may later issue a pinned read-only Work Order
through existing Issue #981 after the trust boundary is reviewed.
Replace both SHA placeholders with the exact current PR #1443 HEAD.

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
  "monitor_summary": "SWPC Control Station readonly status",
  "objective": "Observe installed Control Station state without mutation.",
  "acceptance": "Record real Run/Job/exit/installed identity; no writes."
}
```

This document does **not** authorize a deploy Work Order. The fixed
bridge and local Controller must remain in separate security domains.
After any future owner-approved source upgrade, separately verify
release/rollback pin, Manager+Console health, PPU transaction ownership
and HIL evidence. All such operations are currently NOT_RUN.

## Host-only regressions

Tests cover exact source SHA, wrong host, dirty/untracked checkout,
immutable command vector, no arbitrary privilege escalation, forbidden
deployment and extra arguments, permission denial, timeout, and no retry.
CI success is never substitute for physical or live SWPC qualification.
