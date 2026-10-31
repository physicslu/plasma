# PLASMA Path 3 — SWPC Codex Execution Contract

**Status: Normative route-specific contract.** Root [AGENTS.md](../../AGENTS.md) and the [shared contract](plasma-development-common.md) remain authoritative for approvals, Git, safety, credentials and recovery. Do not load the Path 2 contract for ordinary Path 3 tasks.

## 1. Executor and route

Path 3 is ChatGPT → authorized GitHub Actions / trusted Development Dispatcher → existing SWPC `plasma-codex` Runner → **Codex CLI** iterative development/test → PR and relevant CI → ChatGPT independent evidence review. Select it when SWPC access and autonomous diagnosis, cross-module edits or repeated fix/test are needed. Keep the existing Path 3 identity; ChatGPT Direct is the default, not numbered Path 1. No new Runner, per-device session, Host Supervisor or Stage/Profile middleware is required.

## 2. Work Order and exact authorization

Gate 1 authorizes the bounded task, source/ref/PR HEAD SHA, executor, device/resources, acceptance and safety/recovery. The trusted dispatcher remains bound to reviewed main code; candidate execution uses the exact owner PR HEAD and SHA/digest-pinned Work Order. Choosing Path 3 grants neither Linux root nor unrestricted hardware use. Do not add another Ready, hardware or deployment approval Gate. Gate 2 is solely the merge approval. A material change of task scope requires revised Gate 1.

## 3. Codex CLI, sandbox and native tools

Codex owns implementation, real execution, self-tests, failure diagnosis and repair under Gate 1. Default `--sandbox workspace-write`; only an Owner-authenticated, SHA/digest-pinned dynamic hardware Work Order with `codex_execution: guarded-hardware-no-sandbox` selects the reviewed one-shot `--sandbox danger-full-access` mode. This changes sandboxing, **not** the worker's Linux DAC/ACL, root authority, electrical safety or device ownership.

Use native CLI, SSH, USB/TTY, Sigrok and project build/test tools within the approved scope. Do **not** reinstate retired JSON Host Supervisor, fixed operation adapters, LA-only launchers, per-device Stage/Profile/Probe allowlists or a separate resume layer. LA2016 and Z2 are examples, not an allowlist. Consult [Path 3 native hardware tools](plasma-path3-direct-hardware-tools.md) when relevant. The worker's actual USB/device permissions and device-specific native busy/claim checks remain mandatory.

## 4. Z2 SSH/sudo and hardware boundary

Use the existing owner-controlled local credential source described in the [shared contract](plasma-development-common.md), never commit, print, log or copy secrets into PR artifacts. SSH/sudo must use the enrolled owner-approved route and actual Linux rights; no sudoers edits or sandbox bypass. For approved FPGA work, validate current board/boot, candidate BIN/Manifest and SHA, Root/FPGA Manager ownership, safe output/electrical state and Golden recovery. Path 3 may perform bounded development deployment/FPGA operations only when included in Gate 1. Z2 PS, not SWPC, hosts live DUT OpenOCD and PS-local WordPort; PL performs DUT I/O. Internal-loopback evidence is not external SWD/DUT qualification. On unknown/unsafe state stop and report NOT_RUN/FAIL accurately.

## 5. Autonomous fix/test loop

Execute **Build → Run → Observe → Fix → Retest** until acceptance PASS or an actionable real blocker, without requesting redundant user `continue`. Reuse prior valid evidence and avoid full review for unchanged HEAD. A physical test requires authentic current-state evidence; a mock or CI PASS cannot substitute for SWPC/Z2/DUT acceptance. After a proven safe FPGA Download, Keep Loaded is the normal default; functional FAIL alone does not trigger Golden Restore. Stop further DUT activity, reap tools and preserve safe ownership on failure; invoke recovery on documented need.

## 6. PR, CI and evidence

Codex may prepare branch/PR under approved scope; ChatGPT independently reviews source, test logs, artifacts, hardware status and PASS/FAIL. A PR created using `GITHUB_TOKEN` does **not** guarantee `pull_request` workflows run; verify actual required CI checks or use an already reviewed trigger route. Before Gate 2, complete all in-scope acceptance, record exact HEAD, Runner/Run/Job, exit status, hashes and recovery when applicable, and resolve failures. Never merge without Gate 2; never infer deployment or physical success from PR/CI status.

## 7. Shared clauses retained by reference

Read relevant sections of [shared contract](plasma-development-common.md) for two-Gate policy, trusted source, credentials, Root Guard, Git, CI, safety and failure handling. The shared contract preserves cross-route rules and does not grant additional hardware authority.
