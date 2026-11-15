# Control Station owner bridge — administrator-only staging and rollback

**Gate 1 / Draft only. Not installed, not activated, not hardware-qualified.**

This is an operator-run installation contract, **not** a Path 2 Work Order.
The Runner is never authorized to install the bridge, change sudoers, edit
owner services, modify source checkouts, or execute a shell as the operator.

## Candidate and installation trust

The source artifact is `scripts/plasma_cs_owner_bridge.py` from an
explicit owner-reviewed Git commit. The trusted administrator must independently
confirm the file's exact SHA256, root-owned installation, protected parent
directories and no symlinks before enabling the narrowly scoped policy.
The installed executable is a fixed root-owned, non-writable file at
`/usr/local/libexec/plasma/plasma-control-station-owner-bridge`.

**Illustrative trusted-administrator steps only, do not run from GitHub Actions:**

```bash
# Admin console, after immutable SHA review:
sudo install -d -o root -g root -m 0755 /usr/local/libexec/plasma
sudo install -o root -g root -m 0755 scripts/plasma_cs_owner_bridge.py \
  /usr/local/libexec/plasma/plasma-control-station-owner-bridge
sudo stat -c '%U:%G %a %n' \
  /usr/local/libexec/plasma/plasma-control-station-owner-bridge
sudo sha256sum /usr/local/libexec/plasma/plasma-control-station-owner-bridge
```

Before enabling the owner-run rule, verify every privileged file and
parent path is root-owned and not writable by the Runner; inspect the
actual `/storage` operator checkout ownership, the operator's user
systemd runtime, and sudoers baseline. Use `visudo -cf` for proposed
policy and retain its previous hash and a reversible backup. No private
credentials, arbitrary environment, or wildcards belong in arguments.

**Sudoers policy template, NOT an installed policy:**

```text
# Replace role placeholders in the trusted administrator channel only.
<runner-user> ALL=(<operator-user>) NOPASSWD: /usr/local/libexec/plasma/plasma-control-station-owner-bridge status, /usr/local/libexec/plasma/plasma-control-station-owner-bridge verify
```

Policy must contain *only* these two exact argument vectors. Do not
permit unrestricted `bash`, `git`, `python3`, `env`, `systemctl`,
`sudo -u`, `SETENV`, `ALL`, or extra arguments.

## Runtime and failure semantics

The fixed bridge starts only `status` or `verify` under the operator
user identity, a fixed Control Station Bash backend, and a minimal
known environment. It confirms its immutable installed path and the
caller identity provided by sudo; rejects untrusted user checkout,
mutable/symlinked bridge or absent user-systemd session.

These are **read-only** operations in the scope of Control Station
observability. `deploy`, `install`, `rollback`, `shell` and all
unknown arguments exit 77 before calling any backend. A successful
read-only invocation is NOT an authorization to restart Manager, enable
new programming admission, operate Z2 or flash DUT.

If Bridge admission fails, report `NOT_RUN_PERMISSION_DENIED` or the
observed failure classification and never retry blindly. Record source
SHA, Runner/Job/exit, installed file SHA, operator checkout source,
Manager/Console health and configured PPU state, without secrets.

## Rollback

With trusted operator approval, revoke the exact-argv sudoers fragment
before removing the installed bridge. Verify the fragment is gone and
no Runner can invoke the bridge; preserve receipts and previous sudoers
hash. Remove only the bridge file installed through this runbook and
leave operator-owned user-systemd services, runtime release, preserved
journals, enrolled Z2 and DUT unchanged.

## Separate deployment qualification

A **later** deploy-capable bridge version requires its own Gate 1 and
Gate 2 source review, actual maintenance/admission exclusivity and
pre/post immutable transaction evidence. Neither owner intent nor two
read-only snapshots prove atomic quiescence. PR #1435 still finds six
legacy consumed Starts in an incompatible live Manager; PR #1444's new
reconciliation source is Host-only and cannot by itself unblock that
active old Manager. Do not bypass the hold by deleting history or
silently marking UNKNOWN as PASS.
