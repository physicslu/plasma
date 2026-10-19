# PLASMA — SWPC Codex device-permission diagnosis: Run #39190291831

## Incident evidence (already verified)

GitHub Actions [Run #39190291831](https://github.com/physicslu/plasma/actions/runs/39190291831)
(merge SHA \`a2a0b3b2e3df376bccfc150e9bf46829187eeb0e\`) reached
dedicated \`SWPC-plasma-codex\` on 2026-10-19.

- Hosted contract SUCCESS, hosted provenance authorization SUCCESS.
- SWPC \`codex\` job started; Linux identity and GitHub event admission PASS.
- Device preflight emitted \`NO_GO: software Codex can access a hardware device\`
  (exit code 2). It printed **no device name**.
- Real Codex, GCC, patch upload and hosted Publisher did **not** run.
- Original check stops at the FIRST \`/dev\` node satisfying
  \`test -e "$device" && (test -r "$device" || test -w "$device")\`.
- The culprit path and whether access comes from world/group/ACL/udev
  are **not known** from that original log.

This PR only implements a way to collect the missing evidence; it does NOT
claim the specific device or its permissions have been observed.

## Proposed exact, non-invasive observation

- Diagnostic code:
  \`scripts/plasma_codex_device_permission_diagnostic.py\`
- Workflow:
  \`.github/workflows/plasma-codex-device-permission-diagnostic.yml\`
- Offline tests:
  \`scripts/tests/test_plasma_codex_device_permission_diagnostic.py\`
- Read exactly the SAME seven patterns and in the SAME order as the failed
  software-only preflight: \`/dev/mem\`, \`/dev/uio*\`, \`/dev/ttyUSB*\`,
  \`/dev/ttyACM*\`, \`/dev/hidraw*\`, \`/dev/gpiochip*\`,
  \`/dev/bus/usb/*/*\`.
- Use only \`os.stat\` / \`os.access(... effective_ids=True)\` and optional
  \`getfacl -cp\` (POSIX ACL metadata). **Never open, read or write the
  device itself. Never call ioctl, udevadm trigger or access DUT/FPGA.**
- Report exact *current* first culprit node, all matching accessible
  nodes, current Linux effective user/group memberships, Unix mode,
  inode owner/group, effective read/write access, and ACL if available.
- Output an evidence artifact under \`RUNNER_TEMP\` with 3-day retention,
  plus a concise Actions summary. No environment dump or device payload.
- An accessible node gives NO-GO; **readable is not automatically
  controllable**. Failure to reproduce means the permissions may have
  changed since the original run, NOT that isolation is certified.
- Cannot fully establish udev rule provenance, authorization by a
  privileged daemon, lab network reachability, or sandbox isolation.
  Those are separate investigations; do not weaken the failed guard.

## Execution gates and scope

**Gate 1, this PR:** Review the script, workflow, tests and documentation.
GitHub-hosted offline PR CI may run. No SWPC diagnostics, model, HIL,
deployment, device access or system setting changes may run.

**Gate 2 for this implementation PR:** Approve ONLY the code merge.
Ordinary \`push\` to main runs the hosted contract only. The SWPC \`inspect\`
job is skipped. Merging this PR is NOT authorization to run the scan.

**Separate future permission needed:** User explicitly approves the read-only
SWPC snapshot. An OWNER-initiated \`workflow_dispatch\` on **main** must
choose exact original run \`39190291831\` AND confirm the read-only
diagnostic boolean. Hosted \`authorize\` must pass; \`inspect\` then runs
ONLY on \`[self-hosted, linux, x64, plasma-codex]\` under the unprivileged
\`plasma-codex\` user. No generic issue comment, reboot, service reload,
\`sudo\`, runner provisioning, Codex CLI, GCC, Publisher, git push or
hardware operation is part of that inspection.

Workflow reruns (\`GITHUB_RUN_ATTEMPT != 1\`), wrong actor, other branches,
different input run number, or disabled confirmation **do not schedule
the SWPC probe**. The in-worker identity check fails closed as well.

## Interpreting results

- \`NO_GO_REPRODUCED\`: current node metadata reproduces the old
  *accessibility predicate*, with the first triggering path recorded.
- \`NO_GO_NOT_REPRODUCED\`: no current matching node has effective
  read/write access. Original historical failure remains proven;
  do not infer it was false or conclude SWPC is fully isolated.
- \`NO_GO_METADATA_ERROR\` / \`NO_GO_TOO_MANY_NODES\`: incomplete
  evidence; do not release a software-only worker.
- ACL \`NOT_CHECKED\`: cannot attribute access to ACL. Compare
  owner/group/mode and explicitly investigate rules or ACL through a
  separately authorized read-only follow-up.

This PR does not relax the software-only preflight or authorize a rerun
of the failed real Codex job. The C Hello World source remains uncreated.
