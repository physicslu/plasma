# PLASMA — SSH tmux Engineering Monitor (Path 2 / Path 3)

**Scope:** Development Mode, owner-only operator view. One tmux session,
two switchable windows (Path 2 and Path 3). This is not another dispatcher,
workflow, runner, approval gate, HIL test or production service.

## Gate 1 Execution Detail (candidate PR #1195)

Operator-only `L` opens a bounded execution detail view; `J` and `K` scroll
older/newer history. Summary remains the default. For Path 2, the existing
wrapper forwards original subprocess stdout and stderr **unchanged** to the
GitHub Actions evidence sink, while projecting only *completed, validated*
lines to the monitor as distinct `[P] STDOUT` and `[P] STDERR` observations.
Path 3 projects Codex-reported incremental `aggregated_output` as
`[C] COMBINED`, **not** independent stdout/stderr. Simple accepted native
CLI commands can be shown with validated arguments; shell constructs,
unknown commands, addresses, credentials, long lines, ANSI controls, URLs,
and suspected secrets are not mirrored. Detail lines have bounded length,
count and a second parser-side validation. Missing/incomplete details remain
an explicitly restricted observation, not proof of execution or acceptance.

This is **not** a lossless terminal mirror or an evidence authority. Line-based
redaction cannot prove that an arbitrary unknown secret is safe. Secrets in
unlabelled benign-looking output are residual risk; operators must keep raw
session evidence private and should not print credentials to CLI stdout.
Monitor still does not execute, authorize, retry or change hardware operations.
The actual stdout/stderr and physical PASS remain authenticated by existing
Runner/Work Order evidence and separate acceptance. Real SWPC/tmux acceptance
is `NOT_RUN` until separately authorized activation. No deployment/hardware
operation is included in this PR.

## V3 operator layout and result semantics

The path label and all shortcuts occupy **one header row**:
`PATH 3 | SWPC Codex | L Activity | C Clear | Ctrl+A 1/2 Switch | Ctrl+A D Detach`
(with the actual tmux prefix). Both paths show STATUS, RUN, TASK, GOAL,
STAGE, DOING and RECENT ACTIVITY. Path 3 shows a pinned-work-order
capability category `STAGE: Codex workspace` when available; this does
**not** mean Vivado synthesis/implementation/bitstream generation was observed.
Path 2 retains its authorized fixed-stage category.

`WRAPPER: PASS EXIT: 0` is the result of the monitored top-level process,
**not** acceptance of the Work Order, a verified test receipt, PR readiness
or an indication that every Codex command succeeded.
On adequately tall panes `ACCEPTANCE: UNVERIFIED BY MONITOR` makes this
distinction visible next to the Wrapper result, even for exit 0.
`LAST STEP` is the most recently completed sanitized Codex item, whereas
`LAST ERROR` retains the most recent Codex-reported failing item from a
bounded 512 KiB scan of the transient log. The latter can fall outside
retention on a long run; a new run truncates prior monitor history.
These events have trust class `[C]`, never independently verified `[V]`.
Their exit codes are observed Codex values, and neither stderr nor root-cause
details are available to this monitor. Do not infer a failure cause from the
exit code alone; inspect authorized task evidence when necessary.

A small set of whole-command patterns produce fixed semantic labels such
as `Inspect source files (arguments redacted)`, `Run Python tests` or
`Run Vivado batch build` (also redacted). Path 3 additionally recognizes
native executable prefixes for Sigrok (scan, device inspection, acquisition),
OpenOCD, SSH, USB/udev inspection, Python, Git and shell commands.
Arguments, absolute paths, remote destinations, shell operators, stderr,
prompt/model text and credentials are never copied into public events.
Commands containing unsafe shell syntax or which cannot be classified remain
`(command hidden)`. These fixed labels describe only **Codex-reported
attempts**, not permission, actual device response or successful acquisition.

### Path 2 native preflight denial receipts (V3)

The trusted Runner already redirects the Path 2 Dispatcher JSON receipt to
`$RUNNER_TEMP/plasma-path2-receipt.json`. After the wrapped process exits,
the Monitor may **read but never modify** that fixed file. The projection is
limited to the existing native Codex preflight permission denial with exact
`github_run_id`, `task_id`, `work_order_sha256`, nonzero exit code,
permission-safe file ownership/type, and bounded JSON size.
The Monitor copies **only** the fixed category values `NATIVE_PATH_PERMISSIONS_DENIED`,
`CLI_WRAPPER/CLI_MANIFEST/PLATFORM_MANIFEST/NATIVE_BINARY`,
`OWNER_MISMATCH/PEER_WRITABLE` and the component index (1..24).
Other statuses, arbitrary errors, paths, raw stdout/stderr and sensitive
JSON fields are never rendered. Rejected or unavailable receipts omit the
hint without changing the authorized job outcome.

The additional line looks like:

```text
WRAPPER: FAIL  EXIT: 2
RECEIPT: NATIVE_PATH_PERMISSIONS_DENIED | CLI_WRAPPER | PEER_WRITABLE | #1
```

This is a **sanitized Runner receipt hint**, **not** a new verified `[V]`
source. A matching source identity and fixed enum do not prove electrical
or execution safety, and this preflight denial states no model or hardware
work was run. The index is not a host pathname. The line is available only
for future runs after the new trusted main implementation is activated;
an old transient V2 snapshot is not retroactively enriched.

## Operator workflow (SWPC)

After this change is merged to trusted main and an already authorized SWPC
checkout is updated, log in as the trusted operator:

    ssh "${SWPC_OPERATOR}@${SWPC_HOST}"
    cd "${PLASMA_REPO:?set trusted checkout path}"
    # First use creates and attaches the operator-owned two-window session.
    bash scripts/plasma-engineering-monitor.sh
    # Subsequent uses (no window switching):
    tmux attach -t plasma-monitor

The status header shows the configured tmux prefix and shortcuts:
press **C** (no prefix) to clear only the current window's displayed output,
while continuing to show new messages. Press **tmux prefix, then 1** to
switch to Path 2 (fixed CLI), **prefix, then 2** for Path 3 (Codex),
or **prefix, then D** to detach without stopping a GitHub Actions job.
Press **L** without the prefix to switch between a concise activity overview
and an expanded sanitized start/completion trace; press it again to return.
Repeated `item.updated` events are dropped, and the overview collapses
completed RUNNING/DONE pairs. The trace has seconds-resolution timestamps
for new events, but is **not** a raw command-output viewer.
When a valid GitHub Run ID is available and the pane is tall enough,
`RUN LOG: https://github.com/physicslu/plasma/actions/runs/<id>` gives
a copyable evidence entrypoint; it does not certify task success.
The default prefix is Ctrl+B; custom configurations such as Ctrl+A are
detected and displayed in the header. Clearing never truncates a monitor
log, removes Codex evidence, changes job state or affects the other window. IDLE means no observed worker wrapper is currently
running on that path. When a task runs the pane shows its Run ID, task ID,
elapsed time, and recent output. When it finishes, the pane returns to IDLE
and retains WRAPPER: PASS/FAIL with the top-level process exit code.

Both panes use the same compact operator layout: `STATUS` and `RUN` on
one row; `TASK` and optional `PR` on one row; `GOAL` and `NOW`,
a single `DOING` activity row and `RECENT ACTIVITY`. PATH 2 currently
has only legacy heartbeats/Stage labels; its `DOING` line explicitly says
per-step telemetry is unavailable while the dispatcher is running. PATH 3
can display filtered Codex command/file activities. The active-stage category (when applicable),
elapsed time or
LAST/EXIT, SWPC host-local NOW (`YYYY-MM-DD HH:MM` without the ISO `T`
separator or numeric UTC offset), and recent output. The input clock remains
timezone-aware internally and changes the visible minute only once per minute. Rows are clipped
by display **cells** (CJK full-width characters consume two cells),
not by Python character count. The content uses at most 100 display columns
and reserves the terminal's last physical column to avoid autowrap;
smaller terminals clip rather than wrap. On short panes the viewer
omits decorative separators and, if necessary, keyboard-shortcut hints
before losing the latest log row, including when PR, GOAL and STAGE
are all present. This affects only the viewer, not stored monitor files,
Source, Work Order or Evidence.

PATH 2 additionally shows `STAGE`: a fixed label from the already-authorized
execution capability: `CPU-only CLI`, `Native preflight`,
`Vivado host build`, or `Guarded Download/Test/Restore/Full HIL` for a
previously authorized exact stage or existing fixed Registry task. This describes the **approved CLI
category**, not confirmed physical progress. It never reveals a shell
command, argv, raw stdout or hidden script arguments. Detailed Path 2
subprocess evidence stays in existing GitHub artifacts, not the monitor.
For an SHA-bound dynamic CPU-only or operator-cli Work Order, the existing
Authorizer also exposes its validated, repository-relative Python entrypoint
as `AUTHORIZED SCRIPT` (display-only). It is an approved **target** script,
not proof that its body has started or any subprocess step has completed.
`Guarded CLI` is the current operator-cli category; it is not a new Root
capability. Paths, argv and commands not explicitly covered by this bounded
metadata are not inferred or displayed.
If there is no recognized category, the pane shows
`STAGE: (not available)`.

A dynamic Path 2 or Path 3 owner Work Order may explicitly include an
optional `monitor_summary` string: 8–80 simple display-safe characters.
It is validated and SHA-256-bound with the immutable Work Order by the
existing Authorizer and passed as operator-only metadata. Do not place
secrets, network addresses, commands or private task content in this field.
Older Work Orders remain valid but show
`GOAL: (operator summary not provided)`; the renderer never guesses from
raw `objective`, `acceptance`, prompt or command arguments.

### Viewer startup failure and recovery

**PATH 3 missing-window detection:** An operator-observed failure
(`can't find window: 2`) was reproduced using an actual tmux server
on a private socket. `tmux display-message -t session:path3` may return
success by falling back to the existing current PATH 2 window, although
PATH 3 does not exist. The launcher now checks the exact window **name**
using `tmux list-windows` and `grep -Fxq path3`. This only affects
whether a *missing* PATH 3 viewer is created; existing PATH 2/3 panes
are preserved and never sent commands or restarted.

The launcher preserves a Path 2/3 tmux window if its `sg` or Python viewer
terminates immediately. The pane shows `MONITOR_VIEWER_EXIT path=... exit=...`
along with the original error, and falls back to an operator-owned shell
instead of disappearing and misleadingly reporting `can't find window: 2`.
The launcher does not automatically retry or restart the Codex worker.

If the viewer exited, inspect the error in that window first. After resolving
the cause, close **only that diagnostic pane's shell** (for example with
`exit`), then run `bash scripts/plasma-engineering-monitor.sh` from a
separate operator shell to recreate the missing viewer. An already-running
Path 2 or Path 3 window is never replaced by the launcher; do not use
`tmux kill-server`, do not kill other sessions, and do not mutate the
underlying monitor logs or job evidence.

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
governed by task/build evidence policy. Path 3 uses `codex exec --json`.
Its persisted `.plasma-path3-evidence/codex.log` remains **event type
names only**. The transient operator observer log additionally contains
`@PLASMA_ACTIVITY_V1` records for recognized, well-ordered Codex
`command_execution` and `file_change` item events. Only strictly
allowlisted whole commands (selected Python tests and read-only Git status
commands and recognized native executable classes), validated
repository-relative file names, their reported
lifecycle states, and (for completed commands only) the Codex-reported
integer exit code may be shown. The exit code is **observed**, not a trusted
Runner or test Receipt. Unapproved commands become
`(command hidden)`; unsafe file names become `(file paths hidden)`.
Neither raw JSON bodies nor stderr, prompts, tool arguments, model text,
source code or execution output are copied into these logs.

**Visibility limit:** The Monitor reports recognized native tool actions,
their Codex-observed start/completion, exit code and the GitHub Run link.
It cannot infer hardware success, sample counts, physical results or error
causes without safe structured receipts. Streaming arbitrary native stdout,
stderr or raw Codex transcripts would change the information-disclosure
boundary and is intentionally outside this lightweight observer update.

The `[C]` marker means observed **Codex JSON event**, NOT independently
verified execution evidence or a trusted testing receipt. `[V]` is
reserved for a future verified-Receipt adapter and is not emitted by
Phase A. An `item.started` without a matching completed event is never
shown as a verified success. Unknown fields, missing IDs, duplicate start
and out-of-order completion fail closed. The activity collector tracks at
most 64 unfinished items; any further orphaned starts are ignored until
capacity becomes available. The Viewer drops replayed/decreasing sequence
numbers and never prints malformed structured records verbatim. No command text is executed by
this projection or taken as approval for hardware work. The dispatcher
extracts only `thread.started.thread_id` as the Codex Session ID and the
non-negative token counters from `turn.completed.usage` into
`.plasma-path3-evidence/codex-token-usage.json` and the hashed JSON receipt:
`input_tokens`, `cached_input_tokens` (already included in input), and
`output_tokens`. Missing or invalid usage is `null`/`unavailable` or
`invalid`, never a fabricated zero. This does not read Codex auth/session
files or modify its session, sandbox, Runner, permissions, or task routing.
Existing source diff, evidence hashes, failure semantics and artifact
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

1. SSH to SWPC, start or attach the two-window tmux session.
2. With no observed Path task, confirm both windows show IDLE.
3. Run an already authorized Path 2 CPU-only task; confirm Run ID,
   RUNNING, IDLE, GOAL/fallback, the fixed CLI STAGE, timezone NOW,
   exit/result and independent GitHub evidence.
4. Repeat for an authorized Path 3 CPU-only job and verify sanitized
   Codex event types appear while running (not only after it exits).
5. Verify switch (prefix+1 / prefix+2), C clear (new messages still appear,
   monitor/evidence logs preserved), detach/reattach, stale-run handling and existing Artifact,
   and confirm no unauthorized resources were touched. Report
   FAIL or NOT_RUN wherever real evidence is missing.
