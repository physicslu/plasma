# PLASMA — SWD-05 Legacy Dedicated Dispatch Retirement (Gate 1)

**Baseline:** `main` `25a3055da4e095d889c4bc021ac50507b4610c26` (merged PR #1151).  
**Status:** Draft PR, GitHub-hosted tests only; no merge, deployment, private-file deletion, SWPC runner job or physical Z2/FPGA/USB/DUT operation.  
**Purpose:** Retire the historical Issue #981 **dedicated SWD-05 supervisory dispatch** without removing the production SWD-05 transaction driver or the shared FPGA protection contract.

## 1. Dependency inventory and disposition

| Component | Existing function / incoming dependency | Gate 1 decision |
| --- | --- | --- |
| `.github/workflows/plasma-codex-z2-swd05.yml` | Exact `/plasma-codex z2-swd05 981` comment authorizes a dedicated `oneshot` job on the shared worker. No shared Path 2/3 dispatcher calls it. | Delete the dedicated owner dispatch after reviewing references and CI coverage. |
| `scripts/plasma-codex-z2-swd05-contract.py` | Owner-only event and fixed runner contract used by dedicated workflow. | Delete with its only caller. |
| `scripts/plasma-codex-z2-swd05.py` | Loads obsolete private `z2-swd05-oneshot.json`, assembles separate SSH/sudo root `one_shot` command; invoked by dedicated shell wrapper. | Delete dedicated host launcher; do not replace with another privileged bypass. |
| `scripts/plasma-codex-z2-swd05.sh`, `scripts/plasma-codex-z2-swd05-inner.sh` | Dedicated tmux wrapper and launch script only. | Delete with dedicated workflow. |
| `scripts/tests/test-plasma-codex-z2-swd05.py` | Dedicated launcher/receipt tests **and** PR #1151 credential-consolidation regressions. | Retire dedicated launcher tests, **move credential regressions** to `scripts/tests/test-plasma-codex-z2-login.py`; preserve `pl/tests/test_swd05_one_shot.py` separately. |
| `docs/development/plasma-codex-z2-swd05.md` | Dedicated owner command/enrollment/runbook for historical launcher. | Retire; keep this dependency audit and Git history as evidence. |
| `docs/development/plasma-codex-software-mvp.md`, `scripts/tests/test_plasma_codex_software_mvp.py` | Still enumerate retired workflow as a current shared worker workload. | Update the historical workload list and security assertions for retained SW/LA workflows. |
| `scripts/plasma-codex-z2-login.py` | Worker `z2-login-smoke.json` login and legacy credential consolidation still parses SWD-05 route, yielding `BLOCKED_ROUTE_SCHEMA`. | Keep SSH/login and optional sudo password; **remove route reads/mutations** from consolidation. Legacy worker SSH/sudo mismatch still fails closed. |
| `docs/development/plasma-three-path-execution-model.md`, `docs/development/plasma-codex-z2-login.md`, `docs/README.md` | Documentation still defines obsolete Route dependency. | Update only those obsolete assumptions. |

## 2. Important live dependencies: **MUST RETAIN**

- `pl/hil/swd04/one_shot.py` defines `OWNER_LOCK`, `protected` and `manager_last_load`, imported by `pl/hil/path2_z2_target_guard.py`; `scripts/tests/test_plasma_path2_z2_target_guard.py` checks its ownership/lock semantics. **Do not delete or rename its lock namespace `/run/plasma-z2-swd05/`** merely because it has a historical name; doing so could break mutual exclusion with existing root-owned tools.
- `pl/tests/test_swd05_one_shot.py` tests the retained protected supervisor. The deleted dedicated Workflow formerly ran it; move that **Host-only** coverage to `.github/workflows/pl-swd04-hil.yml` before removing its old CI owner.
- `pl/hil/swd04/native_qualify.py`, `software/python/plasma_interfaces/swd_transaction.py`, `software/python/plasma_interfaces/linux_mmio.py`, `software/python/tests/test_swd_transaction_driver.py`, `.github/workflows/pl-swd05-linux-driver.yml` and `docs/development/swd05-linux-swd-transaction-driver.md` constitute a **different retained driver/capability**, not the historical one-shot dispatcher.
- `scripts/plasma_development_stage_transport.py`, `scripts/z2/plasma-path2-root-entry`, `scripts/plasma_development_codex_sandbox.py`, `scripts/plasma_development_dispatch.py` and the trusted Path 2/3 Workflow are **out of scope**. No privileged Z2 Stage, Source Pin, FPGA Restore, safety B1/B2/B3 or GitHub execution gate may be relaxed.
- `z2-login-smoke.json` remains the **sole** worker SSH/sudo credential; `z2-login-known_hosts` remains its public Host Key pin. The removed SWD-05 route is neither another credential nor a prerequisite for a successful SSH login.

## 3. Behavioral and security gates

1. `/plasma-codex z2-swd05 981` loses its dedicated Workflow; do **not** silently remap the command to Path 2 or Path 3. Existing Path 2/3 Work Orders and protected Root Entry remain unchanged.
2. Preserve safety checks for privilege, immutable source, candidate/recovery image, actual FPGA Owner Lock, identity evidence and rollback. Historical lock naming is **not** a reason to change a hardware coordination mechanism.
3. Migrate offline coverage (including denial of accidental authorization by PR/push) to the retained workflow/test contracts; `pl/tests/test_swd05_one_shot.py` must continue running under GitHub-hosted CI.
4. Local `--consolidate` may check worker `z2-dev-credentials.json` strictly and retire only that owned worker login after validation, but must **not** parse, edit, unlink or depend upon any SWD-05 route.
5. Do not interpret removal from the Git tree as deletion of a private SWPC credential/configuration file, Z2 root files, historical GitHub Actions Runs or GitHub evidence. **No automatic SWPC migration or hardware execution**.
6. Negative regressions must prove malformed/outdated SWD-05 route does not block login credential consolidation, credential conflict still blocks safely, and retained shared authorization boundary is intact.

## 4. Gate 2 readiness / evidence

Record exact PR HEAD, full changed file list, `main` divergence, GitHub-hosted Python/PL + docs + retained SWD-04/SWD-05 Driver CI, active Rulesets, Reviews, unresolved Threads and Mergeability. Failures or uncovered actual dependencies hold at Gate 1. This Draft PR is **not** an owner Gate 2 merge or an authorization to operate the SWPC/Z2/DUT.

**Known local evidence:** On SWPC a trusted worker `z2-login-smoke.json` and pinned Host Key produced `Z2_SSH=PASS`. Original `--consolidate` failed with `BLOCKED_ROUTE_SCHEMA`; that was not an SSH failure and cannot justify altering shared HIL safety. No credential files or physical hardware are touched by this retirement PR.
