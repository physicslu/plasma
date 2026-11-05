# PLASMA Path 2 — SWPC CLI Execution Contract

**Status: Normative route-specific contract.** Root [AGENTS.md](../../AGENTS.md) governs approvals, Git, security and evidence; [Embedded](plasma-embedded.md) governs Z2 recovery, and [Common](plasma-development-common.md) covers shared programming and execution zones. This document specifies only Path 2 differences. Do not load the Path 3 contract for ordinary Path 2 tasks.

## 1. Scope and execution boundary

Path 2 is ChatGPT → owner-authorized GitHub Actions / existing trusted Dispatcher → SWPC self-hosted Runner → reviewed deterministic native CLI/Python commands → real result and evidence. Choose it when SWPC execution is required and bounded commands suffice. ChatGPT Direct is the default for source/docs/host-only work; Path 3 is for autonomous Codex diagnosis and iterative implementation. Path 2 **does not delegate execution to Codex**. Keep existing Path 2 identifiers for receipts and compatibility.

### Deterministic Host-only observation (no Codex tokens)

Before selecting Path 3 for an exact, non-interpretive SWPC query such as
`hostname`, prefer the **existing Path 2 `cpu-only` route**. The reviewed
`scripts/plasma_host_observe.py` accepts only one of `hostname`,
`kernel-release` or `python-version`; it never launches a shell,
Codex, SSH, network or device APIs. It runs under the existing Bubblewrap
`--unshare-all` sandbox; observations describe that process's namespace,
which must not be conflated with a privileged or global machine audit.

For an owner-authenticated Issue #981 dynamic Work Order, use:
`execution_path: "path2-cli"`, `capability: "cpu-only"`,
`scope: "host-only"`, `script: "scripts/plasma_host_observe.py"`,
`argv: ["hostname"]`, `verification: "exit-code"`, and a bounded
`timeout_seconds`. Retain the normal `schema`, `objective` and
`acceptance` fields. The code is source-pinned by the existing Dispatcher;
no new workflow, task registry, runner or privilege is introduced.

Exit code 0 verifies command completion, **not the factual correctness of
stdout**: check the stored Path 2 stdout/stderr/process receipt and record
the observed hostname as evidence separately. For an exact predictable
stdout, the existing `stdout-sha256` verification remains available.
GitHub-hosted mocks only prove the routing/sandbox contract; real SWPC
observation is NOT_RUN until separately authorized and executed.

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

Read [AGENTS.md](../../AGENTS.md) for Development Mode, source-of-truth, two-Gate, Git/CI and security; read [Embedded](plasma-embedded.md) for Z2 credentials, hardware ownership, protected Root and recovery.
