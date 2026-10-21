# PLASMA — SSH tmux Engineering Monitor (Path 2 / Path 3)

**Scope:** Development Mode, owner-only operator view. One tmux session, one window,
two simultaneously visible panes. This is not another dispatcher,
workflow, runner, approval gate, HIL test or production service.

## Operator workflow (SWPC)

After this change is merged to trusted main and an already authorized SWPC
checkout is updated, log in as the trusted operator:

    ssh gordon@SWPC
    cd /storage/projects/plasma
    # First use creates and attaches the operator-owned two-pane session.
    bash scripts/plasma-engineering-monitor.sh
    # Subsequent uses (no window switching):
    tmux attach -t plasma-monitor

Press Ctrl+B, then D to detach without stopping a GitHub Actions job.
The left pane always displays Path 2 (fixed CLI), and the right pane always
displays Path 3 (Codex). IDLE means no observed worker wrapper is currently
running on that path. When a task runs the pane shows its Run ID, task ID,
elapsed time, and recent output. When it finishes, the pane returns to IDLE
and retains LAST: PASS or LAST: FAIL and process exit code.

PASS here means only the monitored command exited 0; it does not supersede
independent ChatGPT evidence review or approve a merge. If a process is
killed before writing its final state, the pane shows
IDLE (interrupted/unknown), not fabricated success. Queued jobs or jobs
which fail before the trusted SWPC execute step begins may not appear here;
GitHub Actions remains the authoritative status.

## How the existing jobs publish status

The existing shared workflow .github/workflows/plasma-engineering-runtime-dispatch.yml
runs the trusted main monitor wrapper only for the already authorized
development-execute (Path 2) and development-codex (Path 3) steps.
It executes exactly the same trusted dispatcher command without a shell
or a retry. It publishes minimal JSON status and group-readable live log
in the existing restricted /run/plasma-codex/engineering-monitor/ location.

The wrapper updates status to RUNNING and records an active process.
Path 2 sends a periodic heartbeat; detailed subprocess output remains
governed by task/build evidence policy. Path 3 streams combined real
Codex stdout+stderr simultaneously to its original
.plasma-path3-evidence/codex.log and observer log. Existing GitHub
receipt, source diff, SHA256 evidence, failure semantics and artifact
collection remain unchanged. Monitor failure must not replay Codex.

The monitor checks existing SWPC-plasma-codex worker identity and
plasma-codex:plasma-monitor 2770 directory. If publishing is unavailable,
MONITOR_UNAVAILABLE is logged in the GitHub step and the approved task
runs without monitor support. Never grant sudo or loosen permissions
merely to enable a monitor.

## Boundaries

- No new network port, web UI, Runner, credentials, privileged tmux
  control socket or operator daemon is introduced.
- The tmux server belongs to the logged-in operator and only reads monitor
  files. /run is ephemeral; re-create the tmux session after reboot.
- plasma-monitor is an owner/worker group, not a kernel-enforced read-only
  tmux boundary. Never add untrusted members. Logs may be sensitive.
- GitHub-hosted CI verifies helper semantics but cannot prove real SWPC
  live monitoring. SWPC acceptance is NOT_RUN until an authorized job
  executes with this code after it becomes active on trusted main.
- PR merge does not authorize SWPC deployment, sudo, Runner mutation,
  Z2, FPGA, USB, LA, MMIO or DUT access.

## Real SWPC acceptance checklist (after authorized activation)

1. SSH to SWPC, start or attach the single two-pane tmux session.
2. With no observed Path task, confirm both panes show IDLE.
3. Run an already authorized Path 2 CPU-only task; confirm Run ID,
   RUNNING, IDLE, exit/result and independent GitHub evidence.
4. Repeat for an authorized Path 3 CPU-only job and verify Codex
   output appears while running (not only after it exits).
5. Verify detach/reattach, stale-run handling and existing Artifact,
   and confirm no unauthorized resources were touched. Report
   FAIL or NOT_RUN wherever real evidence is missing.
