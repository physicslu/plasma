# PLASMA Path 3 — SWPC Codex Execution Contract

**Status: Normative route-specific contract.** Root [AGENTS.md](../../AGENTS.md) governs approvals, Git and safety; [Embedded](plasma-embedded.md) governs Z2 credentials and recovery. Do not load the Path 2 contract for ordinary Path 3 tasks.

## 1. Executor and route

Path 3 is ChatGPT → authorized GitHub Actions / trusted Development Dispatcher → existing SWPC `plasma-codex` Runner → **Codex CLI** iterative development/test → PR and relevant CI → ChatGPT independent evidence review. Select it when SWPC access and autonomous diagnosis, cross-module edits or repeated fix/test are needed. Keep the existing Path 3 identity; ChatGPT Direct is the default, not numbered Path 1. No new Runner, per-device session, Host Supervisor or Stage/Profile middleware is required.

## 2. Work Order and exact authorization

Gate 1 authorizes the bounded task, source/ref/PR HEAD SHA, executor, device/resources, acceptance and safety/recovery. The trusted dispatcher remains bound to reviewed main code; candidate execution uses the exact owner PR HEAD and SHA/digest-pinned Work Order. Choosing Path 3 grants neither Linux root nor unrestricted hardware use. Do not add another Ready, hardware or deployment approval Gate. Gate 2 is solely the merge approval. A material change of task scope requires revised Gate 1.

## 3. Codex CLI, sandbox and native tools

Codex owns implementation, real execution, self-tests, failure diagnosis and repair under Gate 1. Default `--sandbox workspace-write`; only an Owner-authenticated, SHA/digest-pinned dynamic hardware Work Order with `codex_execution: guarded-hardware-no-sandbox` selects the reviewed one-shot `--sandbox danger-full-access` mode. This changes sandboxing, **not** the worker's Linux DAC/ACL, root authority, electrical safety or device ownership.

Use native CLI, SSH, USB/TTY, Sigrok and project build/test tools within the approved scope. Do **not** reinstate retired JSON Host Supervisor, fixed operation adapters, LA-only launchers, per-device Stage/Profile/Probe allowlists or a separate resume layer. LA2016 and Z2 are examples, not an allowlist. Consult [Path 3 native hardware tools](plasma-path3-direct-hardware-tools.md) when relevant. The worker's actual USB/device permissions and device-specific native busy/claim checks remain mandatory.

### Explicit quick-observe profile (development-only)

For an **owner-authenticated dynamic Path 3** work order that truly only
observes a small host-local fact, the dispatcher author (not Codex's
natural-language interpretation) may explicitly add both
`"codex_profile": "quick-observe"` and `"scope": "host-only"`.
It is **opt-in**; absent the marker, the unchanged engineering profile
runs normally, including Vivado and long debug tasks. A quick request cannot
select a PR candidate or `guarded-hardware-no-sandbox` and retains
`--sandbox workspace-write`. It must never be used to authorize device work.

A quick run's SWPC Python wrapper enforces a 75-second wall-clock deadline
and stops after more than 12 JSONL tool-item starts. Quick runs fail closed
if the streamed Monitor sink cannot be opened; no unsupervised fallback.
The input-token threshold (30,000) is **post-turn cost telemetry, not a
runtime failure or a live API cost ceiling**: current Codex `exec --json`
reports usage at `turn.completed`, after tokens have been consumed. An
over-budget but exit-zero Codex invocation reports
`status: EVIDENCE_READY_REVIEW_REQUIRED` and
`cost_budget_status: EXCEEDED`, with `functional_acceptance: UNVERIFIED`.
Only a real CLI failure or an enforced wall/tool limit changes the
execution status to failure. The report must never interpret an exit-zero
Codex wrapper as independent functional acceptance. Host-only quick
requests must not be silently inferred from Work Order prose.

The engineering receipt contains bounded, numeric-only
`codex_activity_metrics`: elapsed milliseconds, tool and command counts,
command failures, turns, execution profile, limits, enforcement reason,
cached-share basis points, non-cached input-token count and independent
cost-budget status. No shell arguments, output, prompt or source text
is retained. `codex_context_audit` separately identifies observed Turns
and tool starts, and marks model-request count
`NOT_AVAILABLE` with source reason
`CODEX_EXEC_JSONL_NO_REQUEST_EVENTS`: the available Codex JSONL does
not expose a verified model-request-count contract. Do not mistake Turn
count for individual model requests. `codex_usage` contains reported total
input including cached input, not a billing receipt.

For an exact deterministic host-local observation, dispatch the existing
Path 2 `cpu-only` `scripts/plasma_host_observe.py` instead of launching
Codex at all. See [Path 2 CLI contract](plasma-path2-cli.md). This is a
routing choice by the dispatcher author, **not** an automatic reinterpretation
of the approved Path 3 work order; do not silently change a scoped task.

### Trusted CI Runtime Kit handoff

An authenticated Path 3 hardware Work Order may carry an artifact_source object
containing exactly source_sha (40-digit commit) and run_id (successful Z2 PS
release CI run). The trusted GitHub Actions step checks producer repository,
workflow, push to main, complete source SHA, successful conclusion, Artifact
identity, expiry and ZIP SHA-256. It then verifies the Kit sidecar, complete
internal SHA256SUMS, and embedded PPU release.json source identity. Only
verified Kit and Sidecar paths are exported to the Path 3 subprocess.
The token remains confined to the trusted Actions step. No fixed release is
accepted as a fallback. This does not authorize any Z2 deployment or DUT work,
which still requires the existing owner Work Order scope and Root Guard.

The optional `artifact_sources` field replaces `artifact_source` for an exact
three-artifact handoff (the fields are mutually exclusive). Its executable
validator is `scripts/plasma_trusted_artifact_set.py`; the field schema is
[artifact-sources.schema.json](../../specs/engineering-dispatch/artifact-sources.schema.json).
It pins `ps_kit`, `factory`, and `engine_candidate`, each with repository,
workflow, run ID, artifact ID, actual source SHA, exact GitHub ZIP SHA256,
artifact name, event, branch and PR number. Main push or owner workflow_dispatch
is accepted for Kit and Factory; Engine uses the actual same-repository PR head,
never a claim that the candidate is main. Run attempts other than 1 fail closed.

The existing trusted Actions job fetches and verifies the entire set before
launching Codex. Token-bearing requests and redirects remain in that step;
redirects strip Authorization. Errors are categorical. Only local payload and
sidecar paths plus a sanitized receipt are exported, after all three pass and
files are made read-only. No fallback to a different run or the legacy Kit
route is permitted. Ordinary user OPF bundle admission is unchanged. This
transport alone grants no deployment or hardware authority.

### Operator Monitor engineering diagnostics (display only)

Path 3 Owner-authenticated Issue #981 Work Orders may add optional
`"monitor_phase"` with **only** `HOST_ONLY`, `INSTALL`, `RUNTIME`,
`PROGRAMMING_PROFILE` or `FLASH_TEST`. The trusted GitHub-hosted
Authorizer hashes the full Work Order and emits only the validated enum
to the existing SWPC Monitor wrapper. Absence is `NOT_DECLARED`.
This is **OWNER PLAN**, not a real-time stage transition, hardware
permission, recovery trigger or proof that a stage occurred. A running
pre-change job cannot be retroactively tagged. Existing Work Orders and
the engineering executor operate unchanged.

The existing read-only tmux pane classifies Codex-reported tool events
as `WORK TYPE` (e.g. COMMAND, READ, FILE, TEST, BUILD), displays
`ERROR: COMMAND_NONZERO (exit N) [OBSERVED_CODEX]` on reported failures,
and marks subsequent tool starts as
`FOLLOW-UP: ACTIVITY_OBSERVED; REPAIR_UNVERIFIED`. A subsequent command
is **not** evidence of a repair, successful install, Programming Profile
or real flash operation. Arbitrary shell commands, arguments, source and
credential text remain redacted and are never replayed or parsed for
error causes.

At job completion, the Monitor may read only the fixed, owner/run/digest
bound `plasma-path3-receipt.json` under the Runner's existing temp
directory, under file ownership, size and symlink checks. Only
predefined wrapper `status`, `cost_budget_status` and categorical
failure codes are projected. They are **not independently validated**
execution or DUT receipts. The real engineering report and final
acceptance remain in GitHub Actions Run/Artifact, subject to separate
review: the pane keeps `ACCEPTANCE: UNVERIFIED` even if wrapper exit is 0.
No additional Runner, workflow, privileged process, Codex call, device
access, phase progression or deployment is authorized by the display.

## 4. Z2 SSH/sudo and hardware boundary

Use the existing owner-controlled local credential source described in the [Embedded contract](plasma-embedded.md), never commit, print, log or copy secrets into PR artifacts. SSH/sudo must use the enrolled owner-approved route and actual Linux rights; no sudoers edits or sandbox bypass. For approved FPGA work, validate current board/boot, candidate BIN/Manifest and SHA, Root/FPGA Manager ownership, safe output/electrical state and Golden recovery. Path 3 may perform bounded development deployment/FPGA operations only when included in Gate 1. Z2 PS, not SWPC, hosts live DUT OpenOCD and PS-local WordPort; PL performs DUT I/O. Internal-loopback evidence is not external SWD/DUT qualification. On unknown/unsafe state stop and report NOT_RUN/FAIL accurately.

## 5. Autonomous fix/test loop

Execute **Build → Run → Observe → Fix → Retest** until acceptance PASS or an actionable real blocker, without requesting redundant user `continue`. Reuse prior valid evidence and avoid full review for unchanged HEAD. A physical test requires authentic current-state evidence; a mock or CI PASS cannot substitute for SWPC/Z2/DUT acceptance. After a proven safe FPGA Download, Keep Loaded is the normal default; functional FAIL alone does not trigger Golden Restore. Stop further DUT activity, reap tools and preserve safe ownership on failure; invoke recovery on documented need.

## 6. PR, CI and evidence

Codex may prepare branch/PR under approved scope; ChatGPT independently reviews source, test logs, artifacts, hardware status and PASS/FAIL. A PR created using `GITHUB_TOKEN` does **not** guarantee `pull_request` workflows run; verify actual required CI checks or use an already reviewed trigger route. Before Gate 2, complete all in-scope acceptance, record exact HEAD, Runner/Run/Job, exit status, hashes and recovery when applicable, and resolve failures. Never merge without Gate 2; never infer deployment or physical success from PR/CI status.

## 7. Shared clauses retained by reference

Read [AGENTS.md](../../AGENTS.md) for two-Gate policy, trusted source, Git, CI and safety; read [Embedded](plasma-embedded.md) for credentials, Root Guard and recovery. Neither grants additional hardware authority.

Ordinary Path 3 explicitly pins `--sandbox workspace-write`.
