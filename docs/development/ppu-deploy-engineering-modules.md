# `ppu-deploy` — PPU engineering-module deployment (Gate 1)

Status: **Gate 1 host-only implementation / independent Draft PR**. This
document does **not** authorize deployment, merge, firmware programming or
equipment operation. The product deployment path (`plasmactl`) is separate.

## Scope and ownership

`scripts/ppu-deploy` is a SWPC operator entry point that coordinates an
immutable source bundle across SWPC and Z2 PS. The initial modules are:

| Module | Z2 PS | SWPC |
| --- | --- | --- |
| `wordport` | Reviewed WordPort Python engine/integration files | WordPort engine client |
| `openocd-integration` | Same reviewed WordPort/OpenOCD Python integration | WordPort engine client |
| `abtest` | Same reviewed Z2 WordPort/OpenOCD integration | WordPort engine client and A/B Runner |

The module names are selection contracts, **not independent OpenOCD binary
installers**. This first phase checks the already-pinned Z2 OpenOCD 0.12.0
binary/target configuration but **does not replace them**; changing the
OpenOCD executable, FPGA bitstream, Root Guard or OS policy needs its own
reviewed gate. The currently pinned Native C WordPort ARMv7 bridge
(`libplasma_wordport_armv7.so`) is checked by SHA-256 but **not replaced**;
building/admitting a new bridge binary likewise needs a separate gate.
Exact Z2 file allowlist and permitted module names are
enforced by `scripts/ppu_deploy_target.py`; no arbitrary path or command
selection is accepted.

## Workflow after Gate 2 approval and merge

From a **clean, committed, up-to-date `main`** on the approved SWPC
engineering installation, the operator can run:

```bash
python3 scripts/ppu-deploy plan abtest
python3 scripts/ppu-deploy deploy abtest
python3 scripts/ppu-deploy verify
python3 scripts/ppu-deploy status
# Only when an operator explicitly decides to revert the current release:
python3 scripts/ppu-deploy rollback
```

`plan` is read-only and requires no Z2 access. `deploy` is a **single
operator action** coordinating both systems, not an always-on or scheduled
updater. It is deliberately unavailable on uncommitted branches, dirty
trees, differing local `HEAD`/`origin/main`, or an unverified upstream
`refs/heads/main` (a fresh read-only `git ls-remote` is required). In Gate 1 only `plan`,
syntax and Host-only mocked tests are executed; do **not** invoke `deploy`,
`verify`, `status` or `rollback` against a live Z2 without a separate Gate 2
operation authorization.

`deploy` loads the existing enrolled, host-key-pinned SSH/sudo credentials
through the WordPort engine; it does not create SSH keys, copy secrets,
fall back to permissive host-key checking or install a daemon. The Z2
target-side helper runs under the existing maintenance/root authority,
because writing protected engineering files is a maintenance operation;
Master/engineering application permissions are not silently elevated.

## Safeguards and two-host consistency

1. Construct one immutable manifest: exact `source_commit`, module, SHA-256
   per allowlisted Z2 and SWPC source file, target-helper SHA-256 and
   manifest-derived `bundle_sha256`. The transfer is a bounded ZIP, no
   caller-defined destinations, and the Z2 verifies hashes and exact set.
2. Compare the current SWPC/Z2 bundle IDs; any mismatch **stops before
   mutation**. Stage the SWPC release, preserving the previous release.
3. Z2 requires its reviewed project bundle, pinned OpenOCD executable,
   target config, Native C bridge SHA, and a quiescent `/dev/mem`, `/dev/uio1` and programming
   process owner check. Live Root Guard and equipment mutual exclusion
   remain separate safety controls; this tool does not invoke hardware.
4. Z2 backs up all destination files, installs the exact reviewed files
   atomically, verifies them, and records a unique rollback transaction.
   SWPC activates an immutable release symlink and verifies its own hashes
   plus Z2's matching manifest. A second deploy with the same active ID is
   idempotent.
5. On SWPC activation/verification failure, attempt compensating Z2
   rollback and restore the former SWPC state. If recovery fails or the
   remote state is uncertain, report a blocking failure for operator
   investigation; do not proceed with another deployment. An explicit
   `rollback` restores the prior verified release on both systems.

Code integrity checks, transaction records and source commit records are
deployment evidence, **not evidence of successful Flash programming**.
Programming acceptance remains governed by mandatory OpenOCD Verify,
optional independent Readback, and distinct USB CDC Heartbeat results.

## Limits, Gate 2 items

- Gate 1 CI runs Host-only mock deployments, hash/manifest/path negatives,
  version mismatch, activation-failure compensation and rollback; no real
  SSH, FPGA, OpenOCD, USB, Flash or target operation.
- Gate 2 must review the exact PR HEAD, rulesets, reviews, required CI,
  source pins, Z2 deployment authority and maintenance window. Only a
  separately authorized operator action can perform the first live
  deployment and its observed rollback drill.
- Release symlink and backup directory permissions, actual Z2 ownership,
  reboot behaviour and cross-host failure recovery are **not validated**
  by mocked tests; live verification is mandatory before production use.
