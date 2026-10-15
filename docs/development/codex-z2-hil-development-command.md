# Canonical Codex command: PYNQ-Z2 PSPL-02 / SWD-00 development HIL

This is the **single reusable assignment** for a Codex agent operating on
the owner's real integration host. It inherits the root `AGENTS.md`;
it is **not** a claim that the present `pl.hil.pspl02.runner` loads firmware
or restores the FPGA. The current runner supplies preflight and allowlisted
MMIO stages, while supervised load/recovery must be orchestrated.

## Invocation

With an existing Codex desktop/terminal session that has authorized access
to SWPC and the PYNQ-Z2, **send this task**:

```text
PLASMA / Z2 / HIL-PSPL-02 + SWD-00 / EXECUTE

Read AGENTS.md and docs/development/codex-z2-hil-development-command.md.
The owner has already authorized this internal-loopback PYNQ-Z2 hardware
development experiment within its agreed Gate 1 scope. PR #940's
Development Mode and prior verified enrollment/Identity evidence are inputs,
not new approval milestones.

Execution host: SWPC.
Repository: /storage/projects/plasma.
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
~/.config/plasma/z2-dev-credentials.json
```

Required JSON keys (example values are **placeholders**, not credentials):

```json
{
  "ssh_host": "<actual enrolled board host or IP>",
  "ssh_username": "xilinx",
  "ssh_password": "<owner-provided password>",
  "sudo_password": "<owner-provided sudo password>"
}
```

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
