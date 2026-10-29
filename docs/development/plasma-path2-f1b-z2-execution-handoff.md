# PLASMA Path 2 — Z2 Site 1 F1-B minimal live HIL handoff

> **歷史交接紀錄（2026-10-21），不是現行 Path 3 的執行規格。** 文內早期 F1-B Root Entry 路徑、Stage 順序與已核准測試範圍只適用當時的 Path 2／F1-B 實驗。現行通用 Root Entry 原始碼為 `scripts/z2/plasma-path2-root-entry`，實際 Z2 是否安裝仍需現場驗證。Path 3 可在 Owner Gate 1 範圍內自行規劃 SSH／sudo、FPGA 與 DUT 工程操作；不強制經此歷史 F1-B Stage 路徑，仍須遵守真實 Linux 權限、硬體資源所有權與恢復安全。以根目錄 `AGENTS.md`、現行可信 Dispatcher 及 [三路徑模型](plasma-three-path-execution-model.md) 為準。

**Scope:** historical 2026-10-21 handoff for one owner-authorized Development
HIL using the exact F1-B candidate and `base.bin`. AXI isolation was
**UNPROVEN** under the original bound-passive UIO risk acceptance; no DUT,
LA, power, unrelated hardware or Vivado rebuild was in that scope.

**Current execution contract:** The earlier SWPC Bridge/approved-SHA PIN
installation plan below has been superseded. Development Path 2/3 use the
trusted-main `scripts/plasma_development_stage_transport.py` with the
protected Z2 root entry and on-device source manifest. No Bridge/PIN
installation or update is an execution prerequisite. Historical commands
and risk acceptance do not authorize a fresh physical run.

## Confirmed facts — do not repeat old qualification

- Prior **real** complete F1-B load / 3×read-only MMIO Identity /
  restore passed in [Run #39395142726](https://github.com/physicslu/plasma/actions/runs/39395142726).
  It was a one-process Path 3 sequence, **not** the Path 2 multi-trigger test.
- Candidate F1-B `/lib/firmware/plasma-f1b-owner-20261020-once.bin`,
  SHA256 `c351f668094a2b841426c64681d44c76cb8c14b61766d90a0e10adcf3a22a3c3`.
- Original `/lib/firmware/base.bin`,
  SHA256 `c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c`.
- Fixed BIT SHA256
  `fdbde5c66999a9dab37339587d304b9c16e71a06f1890b24893c8391859cf075`.
- The existing SWPC→Z2 path previously authenticated SSH and privileged
  sudo using the **owner's local credential store and pinned host key**.
  Do not place credentials or unredacted command output in GitHub.
- The last SSH-only Z2 baseline [Run #39522633934](https://github.com/physicslu/plasma/actions/runs/39522633934)
  passed partially with Manager `operating`, but did not establish root,
  current image, AXI quiescence or any new FPGA operations.

## Exact implementation to stage for review

Use **only an immutable, clean** authorized PR #1082 commit. Verify its
exact SHA after choosing the reviewed commit, and transfer the reviewed
tree to a **root-owned, non-group/world-writeable** directory on Z2.
Use the previously reviewed SWPC→Z2 credential/host-key transport; do
not add a runner, modify sudoers, place passwords in argv/history, or
execute Python files directly from a mutable PR checkout as root.

The **only** live implementation for this handoff is
`pl/hil/path2_f1b_minimal_stage.py`, with these existing dependencies:
`pl/hil/path2_f1b_dev_risk.py`, `pl/hil/path2_z2_target_guard.py`,
`pl/hil/f1b.py`, `pl/hil/swd04/one_shot.py`,
`pl/hil/swd04/development.py`, `pl/hil/swd04/contract.py` and
`software/python/plasma_interfaces/linux_mmio.py`, plus their package
initializers and imported local support code. The target program itself
checks root identity, protected source, exact ARMv7 native interpreter,
current process/driver ownership, firmware digests and shared FPGA lock.

Do **not** reuse the old `f1b-path3-z2-hil-once` task/one-shot claim.
The following fixed Stage task IDs and commands are **historical only**:
`z2-path2-download`, `z2-path2-testing` and `z2-path2-restore` are not in
the current Registry. The current dynamic hardware Work Order uses
`operator-cli`; the protected Z2 Root Entry independently verifies its
source manifest and returns an authentic receipt when explicitly authorized.
No GitHub PR checkout may self-install or become a privileged endpoint.

## Three independent manual stage invocations

After the code has been installed at its reviewed immutable SHA and
the trusted root operator verifies fresh Site1 status, invoke the
following **one stage at a time**, on Z2 using the same protected
root environment and source directory:

```sh
export PLASMA_DEV_RISK_ACK=PLASMA_PATH2_F1B_SITE1_20261021_ONCE_BOUND_PASSIVE_UIO
/opt/plasma/python/3.12.13/bin/python3 -m pl.hil.path2_f1b_minimal_stage download
# Separate operator trigger after successful Download; no automatic transition:
/opt/plasma/python/3.12.13/bin/python3 -m pl.hil.path2_f1b_minimal_stage test
# Separate operator trigger after successful read-only Testing:
/opt/plasma/python/3.12.13/bin/python3 -m pl.hil.path2_f1b_minimal_stage restore
```

The string containing `ONCE` identifies the owner's **specific initially
approved physical HIL risk acceptance**; it is not a permanent prohibition
on repeating normal operations in the target implementation. Repeated
Download/Test/Restore within an authorized Development session are
supported, but this handoff does not itself grant additional real HIL
sessions outside the owner's authorization.

**Stop criteria:** unknown firmware/manager state, a changed Boot ID or
candidate/base hash, other active MMIO consumer, unavailable root route,
SIGBUS/stalled or unreaped child, or a failed FPGA Manager write. Do not
blindly retry after uncertainty; preserve the root checkpoint for an
informed physical recovery decision. A verified `base.bin` allows an
idempotent `ALREADY_RESTORED` no-op.

## Historical protected execution prerequisites (historical run not replayed)

- SWPC trusted-main **Stage Transport**:
  `scripts/plasma_development_stage_transport.py` is called by the
  trusted Dispatcher running as the existing unprivileged `plasma-codex`
  worker. It uses already enrolled private SSH/sudo credentials and pinned
  host keys; do not print them, relax permissions or provision new ones.
  The old SWPC Bridge executable and separate approved-SHA PIN are no
  longer runtime dependencies. Existing root-owned host files are left
  untouched; this source-document update neither installs nor removes them.
- Z2 protected code **source**:
  `scripts/z2/plasma-path2-f1b-root-entry`, installed by the trusted
  target administrator at
  `/usr/local/libexec/plasma/z2-path2-f1b-root-entry`, root-owned,
  mode `0755`. Pin reviewed imports in the root-private
  `/root/plasma-path2-f1b-site1-approved` tree with its
  `.plasma-path2-source-sha256` manifest. The root entry checks the
  manifest and exact 3-word read-only native stage command.
- Do not trigger **either** hardware test unless the trusted main
  Dispatcher includes this registration. The GitHub Workflow **runs
  `trusted/scripts/plasma_development_dispatch.py` from current main**;
  code present only in a Draft PR checkout cannot activate it.
  A reviewed integration/merge and root installation are physical
  prerequisites, not evidence of any HIL execution.
- Before any separately approved physical operation, independently verify
  trusted Dispatcher/Stage Transport identity, the Z2 root-owned source
  manifest, current device ownership/recovery and existing SSH/sudo enrollment.
  Do not infer a fresh PASS from historical Path 3 HIL.

## Two required physical HIL modes (owner request 2026-10-21)

Both historical modes use the trusted-main Stage Transport and protected
Z2 root stage executable. They are independent experiment executions using the
previously pinned candidate firmware; no FPGA Build and no DUT/LA/power.
After Mode A's Restore verifies `base.bin`, Mode B can begin. Run the
two modes separately and retain independent receipts; a single old
Path 3 one-shot result **does not** satisfy either mode.

**Mode A: individually dispatched stages (three user commands on Issue
#981, each pinned to the same reviewed PR HEAD).**

```text
/plasma-dispatch run z2-path2-download --pr 1082 --sha <REVIEWED_40_CHAR_SHA> 981
/plasma-dispatch run z2-path2-testing --pr 1082 --sha <REVIEWED_40_CHAR_SHA> 981
/plasma-dispatch run z2-path2-restore --pr 1082 --sha <REVIEWED_40_CHAR_SHA> 981
```

Each command is an independent Owner issue comment/Action run.
Check each authentic `real_z2` root-stage receipt before sending the next.
Expected: `LOADED_AND_HELD`, `IDENTITY_PASS` (three read32, zero
write32), then `RESTORED_VERIFIED` and current `base.bin`.
No automatic transition from Download to Testing.

**Mode B: one explicitly selected Full HIL command** (not a build
request; not the default for ordinary stage tasks).

```text
/plasma-dispatch run z2-path2-full-hil --pr 1082 --sha <REVIEWED_40_CHAR_SHA> 981
```

Its single Workflow run invokes the trusted Stage Transport in
`download → test → restore` order. Require actual stage receipts and
consistent live Z2 Boot ID. If a stage exits uncertain, stop the
sequence; no blind reload or automatic next stage. The result
`REAL_Z2_FULL_HIL_EVIDENCE_REVIEW_REQUIRED` is a receipt for human
review, **not** Production Qualification. The one explicit Full HIL
task has a bounded 10-minute existing SWPC Workflow budget.

**Physical preparation:** the trusted main-based Dispatcher and Stage
Transport must authorize the exact stage and source. Independently verify
the protected Z2 root entry and root-owned immutable Python source/manifest,
current device state, private SSH host key and sudo enrollment without
printing credentials. A Draft PR alone does **not** activate root access;
GitHub-hosted fake receipts are not real HIL. Do not dispatch these
historical example commands without current owner authorization and
verified protected transport/recovery readiness.

**Outcome matrix**:

| Requirement | Mode A | Mode B |
| --- | --- | --- |
| Same approved F1-B BIN/base.bin SHA | Required | Required |
| Physical Z2 Boot ID consistent | Across three Actions | Across internal stages |
| Download F1-B Manager operating | Actual stage receipt | Actual stage receipt |
| Three Identity reads / zero MMIO writes | Actual native child evidence | Actual native child evidence |
| Restore base.bin confirmed | Actual stage receipt | Actual stage receipt |
| No additional Build/DUT/LA/power | Required | Required |
| SHA/exit-code/FPGA state evidence | Three separate runs | One combined run |
| Production qualification claim | Never | Never |

## As-run evidence and acceptance

For each separately invoked stage, capture actual invocation timestamp,
installed Git SHA, remote root UID, boot ID, stage exit code, sanitized
`PLASMA_F1B_PATH2_DEV=` JSON result, target root-owned checkpoint
(`.plasma-f1b-site1-development-state.json`), bounded native child
result and Manager load/restore log evidence.

Accept a **single successful round in each of the two modes** only if:
- Download observed `LOADED_AND_HELD` on actual Z2.
- An **independent** Testing trigger produced exact three Identity
  words (offsets 0, 4, 0x4000; 3 native 32-bit reads, zero writes).
- An **independent** Restore trigger returned `RESTORED_VERIFIED`
  with original Manager/base state, and no unintended DUT/LA/power work.

Host-only fake-device results are **not** equivalent to these results.
If there is no separately authorized installed root route, final result
remains `REAL_HIL_NOT_RUN` with the concrete missing execution boundary;
do not declare success or invoke an untrusted PR as root.

### HIL-13 historical disposition: obsolete Bridge/PIN deployment request

The former Path 3 `swpc_bridge_deployment` option and Bridge/PIN deployment
prerequisite are obsolete. The active Development Work Order rejects that
option; it does not require a Bridge installer, PIN update, new Runner or
credential. Trusted-main Stage Transport and the protected Z2 root entry
remain the hardware execution boundary. If current enrollment, manifest,
root ownership or recovery checks fail, stop and report `NOT_RUN` with the
actual blocker. This supersession neither proves a real run nor authorizes
new hardware effects.

Testing requires a same-boot F1-B loaded state and current image/ownership
checks. A restored `base.bin` is recovery evidence only. Testing rejects that
state before live inspection or the MMIO child, produces no Identity PASS,
and does not automatically Download. When Download is absent from the
approved stage list, stop and report F1-B not loaded; do not invent a Restore
PASS after the failed test or continue to later stages.
