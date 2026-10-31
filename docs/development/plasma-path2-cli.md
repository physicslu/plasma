# PLASMA Path 2 — SWPC CLI Execution Contract

**Status: Normative route-specific contract.** Root [AGENTS.md](../../AGENTS.md) and the [shared contract](plasma-development-common.md) govern approvals, Git, security, evidence and hardware. This document specifies only Path 2 differences. Do not load the Path 3 contract for ordinary Path 2 tasks.

## 1. Scope and execution boundary

Path 2 is ChatGPT → owner-authorized GitHub Actions / existing trusted Dispatcher → SWPC self-hosted Runner → reviewed deterministic native CLI/Python commands → real result and evidence. Choose it when SWPC execution is required and bounded commands suffice. ChatGPT Direct is the default for source/docs/host-only work; Path 3 is for autonomous Codex diagnosis and iterative implementation. Path 2 **does not delegate execution to Codex**. Keep existing Path 2 identifiers for receipts and compatibility.

## 2. Gate 1 Work Order and source binding

Use the existing Owner-approved, bounded Work Order and trusted dispatcher. Bind the exact owner PR HEAD / source SHA, scoped commands, capability, acceptance, environment, and evidence. Issue #981 Development Dispatcher can admit the exact HEAD of an open same-repository owner PR while its trusted entrypoint remains on main. A user-supplied SHA alone does not authorize work. No per-task Workflow, Registry task ID, third approval Gate, new Runner or Stage/Profile layer is implied. After Gate 1, execute the authorized test/fix/retest loop; Gate 2 is only for merging a PR.

## 3. Capabilities and permissions

- `cpu-only`: intentionally OS-sandboxed, no network/hardware; accepts source-pinned Python scripts under `scripts/`.
- `operator-cli` with `scope: guarded-hardware`: exact owner-approved, source-pinned Python script on the existing **non-root** SWPC Runner, under actual DAC/ACL rights. Exit 69 for unavailable prerequisites or 77 for permission denial **before operation** may be classified as NOT_RUN; a command that already attempted an operation cannot be relabeled NOT_RUN.
- Vivado host build: require the existing reviewed project-owned build contract, exact PR HEAD/source binding, verifier and real host-build evidence; a project ID alone is not qualification.
- The separate protected Z2 FPGA Image Root Entry accepts only `operation + source_sha` for its reviewed lifecycle/recovery operations. Never turn it into arbitrary root shell access or infer sudo/SSH/MMIO permission from Path 2.

Path 2 and Path 3 may share the existing SWPC Runner/account where approved scope and Linux rights permit; no automatic privilege escalation or separate SW/HW Runner. Preserve device ownership, electrical safety, verified Golden recovery, Root source/manifest checks and current state. Do not invent a per-device adapter or extra approval stage.

## 4. Execution, evidence and failure

Execute real SWPC acceptance **before Gate 2** if the task requires it. Record actual Runner/Run/Job, source SHA, commands, exit status, expected/observed result, hashes and relevant recovery. Use PASS/FAIL/NOT_RUN only for observed conditions. A GitHub-hosted mock is not SWPC/Z2/DUT evidence. Reuse valid existing results, fix only demonstrated gaps and rerun affected tests. An unavailable dispatcher, denied privilege or unsafe device state is an explicit blocker, never PASS. Never deploy or touch hardware beyond the Owner-approved Gate 1 scope.

## 5. Shared clauses retained by reference

Read the applicable portions of [shared contract](plasma-development-common.md), particularly Development Mode, source-of-truth, two-Gate model, credentials, Git/CI, hardware ownership, protected Root and recovery. The shared contract retains cross-route and historical constraints that must not be silently discarded.
