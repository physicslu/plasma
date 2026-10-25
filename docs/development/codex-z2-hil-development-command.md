# HISTORICAL / SCENARIO-SPECIFIC — PYNQ-Z2 PSPL-02 / SWD-00 HIL

> **Only for the PSPL-02／SWD-00 internal-loopback experiment.** The fixed `IDENTITY → PSPL02 → SWD00` sequence and its no-external-DUT scope are **scenario-specific**, not the execution instructions for all Path 3 Codex Work Orders. Current general Path 3 is the owner Gate 1 assignment passed by `scripts/plasma_development_dispatch.py` under `AGENTS.md`, with Codex free to choose in-scope engineering steps. Existing OS permissions, image/ownership and Golden Restore safeguards remain effective. This historic assignment is not evidence of today's Z2 state.

This is a **historical, scenario-specific example assignment**, **not the
canonical or reusable template for new Path 3 tasks**. It inherits the root
`AGENTS.md`. References to the PSPL-02 runner, preflight, allowlisted MMIO
stages and load/recovery describe the original experiment; inspect the
current implementation before relying on them. This document grants no new
hardware authorization or runtime capability.

## Invocation

**Historical invocation example only:** for the original explicitly approved
PSPL-02／SWD-00 experiment, the assignment text was:

```text
PLASMA / Z2 / HIL-PSPL-02 + SWD-00 / EXECUTE

Read AGENTS.md and docs/development/codex-z2-hil-development-command.md.
The owner has already authorized this internal-loopback PYNQ-Z2 hardware
development experiment within its agreed Gate 1 scope. PR #940's
Development Mode and prior verified enrollment/Identity evidence are inputs,
not new approval milestones.

Execution host: SWPC.
Repository: $PLASMA_REPO (resolve the existing SWPC repository path).
Board: owner's enrolled PYNQ-Z2, resolved from the current lab inventory.
SSH account: xilinx.
SSH/sudo secret: read the owner-approved local credential store defined in
AGENTS.md; do not print credentials or assume they are in Git.

DO THE WORK, not just propose a checklist:
safely update code; reuse and verify pinned artifacts and original recovery;
authenticate SSH and sudo; run one fast Development Mode preflight;
supervise loading the known candidate BIN and validate its new Build ID;
execute PSPL02 and SWD00 on real hardware; restore the original FPGA image
in success and error paths; check original services, FPGA ownership and
recovery state; write compact factual evidence with actual pass/fail.

Use `--profile development`. The allowed sequence is
IDENTITY (new-image smoke only) -> PSPL02 -> SWD00.
Do NOT execute ERROR/RESET, external SWD/DUT/power operations, broad service
restarts, unrelated edits, or destructive workspace changes.
No recurring enrollment, old Identity qualification, review paperwork,
artificial preflight booleans, or extra manual confirmation.

If the existing tools cannot perform the complete approved experiment,
assemble/test a minimal bounded one-shot orchestrator rather than asking the
owner to execute many manual steps. Never turn a script's intent into an
actual PASS claim. On a genuine safety or access blocker, halt safely and
report the single concrete blocker; perform the available recovery first
where appropriate. Do not weaken executable safeguards, forge evidence,
modify sudoers, or expose secrets.

Acceptance requires ACTUAL observations:
Candidate FPGA load PASS; PSPL02 PASS; SWD00 PASS; original FPGA
recovery PASS. Return exact tested build/commit, stage outcome, evidence
location, and any unexecuted stage explicitly marked NOT RUN.
Continue automatically within the already-approved scope.
```

For Codex CLI installations, this text can be passed through the CLI's
`codex exec` prompt mechanism; that alone does **not** grant the process
network or hardware permissions. Use the locally authorized SSH/network
execution environment, not a sandbox bypass suggested by this document.

## Credential interface — configured once on SWPC, not in Git

Canonical **private host file**:

```text
~/.config/plasma/z2-login-smoke.json
```

Required JSON keys (example values are **placeholders**, not credentials):

```json
{
  "ssh_host": "<actual enrolled board host or IP>",
  "ssh_username": "xilinx",
  "ssh_password": "<owner-provided password>"
}
```

- `sudo_password` 為可選欄位：只有 Z2 sudo 密碼與 SSH 密碼不同時才加入同一份 JSON，不可放到另一個登入憑證檔。
- `z2-login-known_hosts` 是同一 Z2 已確認的公開 Host Key 清單，並非另一份密碼檔。
- Legacy `z2-dev-credentials.json` 不再是執行來源；必須先安全遷移到唯一 Worker Login，再刪除舊登入檔。
- Host directory mode `0700`, file mode `0600`, owned by the SWPC user.
- Use the owner-authorized value for `ssh_password` and `sudo_password`;
  they may be identical. The user granted SSH and sudo use for this
  development board; Codex need not request a new per-command approval.
- Resolve `ssh_host` against the known enrolled board and fail on a
  mismatch; do not sweep a subnet or guess the board IP.
- If the owner already supplied credentials in the **active Codex
  execution context**, the agent may create the private file, with
  restrictive permissions, without asking to repeat them. Do not
  recreate or overwrite an existing file silently.
- If credentials are unavailable to that Codex context, report the
  missing **local credential** as a single setup blocker. This
  chat/repository cannot place the password on SWPC automatically.
- Never put plaintext passwords in Git, PR text, terminal arguments,
  shell history, `AGENTS.md`, evidence bundles, CI secrets or logs.
  When automating `sudo -S`, pass the secret only via stdin in the
  authorized SSH session and suppress credential echo.
- A plaintext `0600` credential file is a development convenience, **not**
  an encrypted vault; use SSH key/OS keychain instead if available, and
  replace the default image password before exposing the board beyond the
  isolated development subnet.

## Mandatory autonomous state machine

```text
INIT
  -> VERIFY_REPO_AND_PINNED_ARTIFACTS
  -> AUTHENTICATE_SSH_AND_SUDO
  -> BOUNDED_DEV_PREFLIGHT
  -> SUPERVISED_CANDIDATE_FPGA_LOAD
  -> FAST_NEW_IMAGE_IDENTITY
  -> PSPL02_CONTROL_STATUS
  -> SWD00_INTERNAL_LOOPBACK
  -> FINALLY_RESTORE_ORIGINAL_IMAGE
  -> VERIFY_ORIGINAL_STATE
  -> ACTUAL_RESULT_REPORT
```

1. Reuse prior immutable Identity/Enrollment approval. Check current
   state only when relevant to *this* run. Do not restart a qualification.
2. Prefer to use current PYNQ metadata/FPGA Manager and services without
   changing unrelated shared state. Honor verified artifact hashes,
   driver/UIO ownership, clocks and the current `development` contract.
3. A candidate load or MMIO error must not skip the recovery attempt
   when recovery remains technically safe and available. If no safe
   recovery path exists, report that explicitly; never report recovery
   PASS by assumption.
4. Keep credentials separate from evidence. The report records no
   passwords, hashes of passwords, or copied secret-store content.
5. The current Development Mode deliberately excludes intentional
   AXI SLVERR/RESET stress; these are separate qualification experiments.
6. If an experiment genuinely needs shared service changes, a different
   bitstream, external pins or target power, it is outside this bounded
   task; do not silently broaden it.

## Result format

```text
Board: <actual Z2 identifier, without credentials>
Candidate BIN SHA256: <verified digest>
Load: PASS | FAIL | NOT RUN
New-build Identity: PASS | FAIL | NOT RUN
PSPL02: PASS | FAIL | NOT RUN
SWD00: PASS | FAIL | NOT RUN
Original image recovery: PASS | FAIL | NOT RUN
Actual runtime evidence: <path>
Blocking defect / next engineering action: <if any>
```

**A generated prompt is not an automated FPGA tester.** This file is the
stable operating command for the Codex agent; actual autonomous execution
requires a working hardware-connected agent and orchestration code.
