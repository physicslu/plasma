# Plasma Autonomous Development Contract

This is PLASMA's **primary operating contract** and the **compact Codex instruction entrypoint**. Read it before any code, configuration, documentation, deployment or hardware change. The [complete detailed clauses](docs/development/plasma-autonomous-development-contract-full.md) remain normative and are incorporated by reference. Read **relevant detailed sections on demand**; do not preload the entire detailed document for unrelated tasks. If an operation touches privileges, electrical safety, deployment, Git history or architecture, read the matching detailed clauses before acting. An abbreviated instruction never grants permissions that the full contract or an executable guard denies. For Path 2 privileged Z2 FPGA Manager/MMIO operations, retain the existing Protected Root Entry (`scripts/z2/plasma-path2-root-entry`), which validates `operation + source_sha` and invokes the reviewed `pl.hil.fpga_image_root` implementation. Path 3 may perform owner-approved Z2 SSH/sudo development deployment and FPGA operations via the enrolled credential route with real Linux privileges and hardware ownership/recovery checks; no new Stage or intermediate approval is required.

**Exactly two owner approval gates:** Gate 1 — Plan Approval *before any new implementation*; Gate 2 — Merge Approval for a specific merge-ready PR. No third gate for Ready, hardware, runtime or deployment. Once Gate 1 is approved, autonomously complete all in-scope work and actual acceptance, including fixes and CI; do not request repeated approval. Material scope change requires a revised Gate 1. **Never merge without Gate 2.**

**Default mode: DEVELOPMENT MODE — owner-operated prototype.** Optimize Build -> Run -> Observe -> Fix and the smallest meaningful real result, not ceremonies or production/fleet policy. This does not remove electrical, OS permission, hardware ownership or recovery guards. PASS/FAIL/NOT_RUN must correspond to observed execution.

## 1. Project purpose and canonical domain

PLASMA is a configurable, multi-Site IC programmer; PYNQ-Z2 is the prototype target. Hierarchy: Facility -> PPU -> SITE 1..N (one-based site_id = 1..N); Socket is a fixture, not Site identity. PPU exposes the **Plasma Gateway** service, its **Plasma Gateway API** and **Plasma Gateway Endpoint**. The Linux **Default Gateway** is an unrelated layer-3 next-hop; do not conflate them. The canonical Protocol v3.3 uses PLASMA33 and site_id 1..N; Web REST contract v3 is canonical. **Plasma Manager** implements bounded managed PPU command routing, not a central universal scheduler. Programming Asset is input; Normalized Image is the execution model. Never reintroduce retired zero-based Channel/Programmer identity into production paths.

Repository: pl/ FPGA and verification; software/python/ embedded/control/REST; software/web/ Console; scripts/ integration and orchestration; docs/ design and operation.

**Hardware execution boundary (normative; CI-enforced):** In the deployed PLASMA system, **SWPC runs Web / Controller / BFF** and sends high-level commands/status over Ethernet; **Z2 PS runs the embedded Linux programming runtime, including the OpenOCD process and its PS-local WordPort/Remote Bitbang bridge**; **Z2 PL executes FPGA SWD/SPI hardware I/O to the DUT**. SWPC may build, package, simulate or host-only test OpenOCD for development but must not run the live programmer backend or forward per-bit SWD traffic to Z2 as the product/physical-PoC path. Paths 2/3 on SWPC are development execution routes, not product OpenOCD hosts. The [PS OpenOCD architecture](docs/architecture/ic-support-openocd-plan-executor.md) is a mandatory code/PR/CI boundary: a change to execution location requires an explicit revised Gate 1 architecture decision and a synchronized architecture contract, implementation and CI test. Keep this invariant separate from production hardware-qualification claims.

## 1A. Prototype-first engineering policy (normative)

Prototype outcomes require the smallest authentic build/test/HIL result. Hosted mocks never prove SWPC, FPGA load, Z2, DUT, voltage or real IC programming. Reuse prior valid board enrollment, identity, artifacts and recovery evidence when applicable, but check current ownership, permissions, candidate identity and actual hazard conditions. Default Z2 internal-loopback HIL to the existing development profile when that HIL is explicitly authorized; qualification profile is only for deliberate qualification.

For healthy normal development aim for at most 180 seconds of pre-experiment checks; this is an objective, **not** permission to omit real safeguards. Preserve legal voltages, current PL/MMIO ownership, artifact identity, rollback image and recovery. Stop on actual SIGBUS, conflicting drivers, dangerous power/voltage, missing root authority or uncertain restoration. Never equate a file hash or CI green check with physical safety.

### FPGA PS/PL Image pairing (normative)

A new FPGA Image is delivered to PS **with its companion Manifest**; the generic protected Root validates the actual BIN SHA256 against that Manifest, applicable Z2 board/FPGA part, ABI/identity, runtime ownership and recovery preconditions. Do **not** reintroduce a per-Image approval token, fixed `approved-fpga-image.json` release allowlist, `runtime_admitted` flag or Root source-commit change per new Image. Source Pin protects **Root executable code**, not the Image data. A valid paired Manifest is consistency evidence, not a cryptographic assertion of publisher authenticity.

**Image A → Image B must support direct FPGA Manager replacement without loading Golden between them**, provided the previous same-boot state and current FPGA Manager provenance are known and the actual FPGA owner/lock and new BIN/Manifest checks pass. Golden remains a recovery resource, not a normal switching gate. Never bypass hardware conflicts, failed loads or UNKNOWN/unsafe in-flight state.

**Keep Loaded is the default after a proven FPGA Download, not a reward for DPIDR PASS.** A protected FPGA Manager Download must have a genuine successful load receipt plus confirmed current-boot identity, exclusive ownership and safe hardware state before the Image may be considered loaded. Once loaded, leave that Image in PL by default, regardless of whether subsequent MMIO Identity/ABI or Blue Pill DPIDR is PASS, FAIL or NOT_RUN; a functional FAIL alone never triggers Golden Restore. On test failure stop further SWD/DUT activity, cleanly close/reap OpenOCD and the WordPort bridge, and release the MMIO lease and owner lock safely; retain the Image for diagnosis only while ownership and electrical/PL output state remain known safe. On failed FPGA load, UNKNOWN/unsafe/in-flight state or an unreaped owner, fail closed: do not blindly retry, access DUT or assume Keep Loaded is safe. Preserve the verified Golden recovery artifact and existing protected Root `restore` capability, but invoke Restore only when explicitly selected or when a documented fault-recovery decision requires it; do not auto-restore merely because an experiment ends or a downstream test fails.

### 1A.1 Development Mode — single-owner, shared-runner, efficiency-first (normative)

- **No overengineering.** Prefer the current Work Order, generic Dispatcher, existing operation transport, proven scripts and Runner. Do not introduce a per-task Workflow, Registry ID, Runner, security platform, evidence system or third approval gate for ordinary development. A genuinely new mechanism with new consequences needs explicit approval in Gate 1.
- **Choose an appropriate Path at Gate 1.** Path 1: ChatGPT Direct for code/docs/Host-only CI. Path 2: SWPC fixed CLI for deterministic real SWPC work. Path 3: existing SWPC Codex CLI for real SWPC plus autonomous diagnosis/repair. Prefer Path 1 unless SWPC required; prefer Path 2 unless agentic iteration needed.
- **Path 2 CPU-only Development Mode:** Dynamic Work Orders may omit `scope` (defaults to `host-only`); verification is `stdout-sha256` with a required digest by default, or explicit `exit-code` without an expected digest. Keep bounded UTF-8 output, argv/timeout checks and the existing no-network/no-device Bubblewrap; source/output evidence is not a physical test. Existing Root authorization, real hardware ownership/locking, image provenance, receipt validation and B1/B2/B3 remain mandatory. No Path 2 Stage/Profile gate or fixed Stage Task ID is needed.
- **Path 3 is not Host-only.** Under an owner-approved Gate 1 Work Order, the existing Path 3 Codex on SWPC may use ordinary USB/TTY tools directly, including OpenOCD, sigrok and CDC, within actual Linux device permissions. Do not add a separate Lab Mode, Session, per-DUT core Stage or execution path. Path 3 may execute owner-approved Z2 SSH/sudo deployment, FPGA Manager/MMIO and hardware tests autonomously when actual OS access, device ownership, electrical safety and recovery allow. Path 2 uses its Protected Root Entry without Stage/Profile admission. If access fails, report NOT_RUN, not PASS.
- Path 2 and Path 3 may share existing SWPC-plasma-codex Runner when the approved task and current host permissions allow. Do not require extra OS/Runner isolation without demonstrated risk.
- **One full readiness review per unchanged PR HEAD.** Revalidate affected deltas and dependencies only. Immediately before an authorized Gate 2 merge, check live HEAD/main, necessary CI, Rulesets, Reviews, unresolved Threads, dependencies and Mergeability. Stop on changes.
- If approved Path 2/3 acceptance requires real SWPC, execute/review it in Gate 1 before merge; GitHub-hosted simulation and a proposed Run ID do not qualify. Preserve actual exit, Run/Job ID, evidence and recovery outcome. Do not merge untested changes merely to trigger a main-only dispatcher. Explicit owner-approved deferral must be documented.
- Preserve only real boundaries: no unapproved deployment, destructive Git, privilege escalation, device operation or credential exposure. Return to revised Gate 1 for materially expanded work.

### 1A.2 Development Mode — shared execution and safety

Use the existing trusted-main Dispatcher, existing Work Order and Runner, not speculative alternate infrastructure. SWPC's ordinary USB/TTY development tools are available to the approved Path 3 Codex process, subject to the worker's real OS privileges, B1 owner/scope authorization and electrical/device-ownership safety. Path 2 direct protected hardware operations retain the existing Protected Root Entry; Path 3 may use the enrolled Z2 SSH/sudo development route for the same approved hardware objective, preserving B1/B2/B3. Authentic exits, hashes and physical evidence are required for any PASS; unknown electrical/recovery state stops unsafe repeats. The [full contract](docs/development/plasma-autonomous-development-contract-full.md) remains authoritative for protected operations.

## 1B. Canonical Codex task/SSH execution contract (normative)

A Codex task is an execution assignment within an approved Gate 1, not a new planning request. Perform accessible authorized tests, diagnosis, repairs and evidence collection autonomously. Do not assume ability to SSH or sudo because credentials exist or instructions request it. Consult the [full SSH and HIL contract](docs/development/plasma-autonomous-development-contract-full.md) and the dedicated Z2 HIL command document for any authorized Z2 task.

Approved Z2 development credentials remain exclusively in the private owner-controlled host credential source. Never commit, print, log, transmit to unrelated endpoints or include in PR artifacts. Do not change sudoers, grant new privileges or use credentials to bypass an actual sandbox denial. Do not invent device IP addresses or operating state. For authorized FPGA load, require candidate identity, known-good rollback and confirmed restoration even on failure; no intentional AXI-fault or external SWD operations in internal-loopback-only tasks.

## 2. Programming data model

Keep canonical Site, Programming Asset, Normalized Image, Job and Batch semantics. A Program operation writes only; Erase, Program, Verify and Read are separately selected. A complete flow states its stages explicitly. Site execution is independent except genuine shared physical resources. Do not infer supported IC models, OpenOCD qualification or board behavior from catalog metadata alone. Consult full contract and domain tests before altering execution semantics.

## 3. Source-of-truth priority

When statements disagree: (1) executable code/check-in config, (2) scripts/plasmactl for integration-host operations, (3) Python/Web package manifests, (4) tests, (5) current architecture/development docs including detailed clauses, (6) historical discussions. Do not silently resurrect stale behavior or stale unsupported claims.

## 4. Execution zones

- **Cloud / GitHub-hosted:** source changes, deterministic host-only tests, PR/CI. Never claim real SWPC, FPGA, voltage, Z2 or DUT success from these.
- **SWPC / integration host:** licensed builds, scoped host validation and owner-authorized USB/TTY experiments by existing Path 3 Codex. Path 3 inherits operator Codex Approval/Sandbox/network settings and the runner's real Linux DAC/ACL device access; no Dispatcher-enforced hardware device allowlist is applied. Check workspace branch/state before changes; never overwrite unrelated work.
- **Z2 / hardware:** real FPGA/PS/PL/DUT operations only with explicit Gate 1 and effective guard/ownership/recovery checks. Hardware observations are not inherited from software success.
- Default workspace is the PLASMA repository. Do not inspect unrelated personal files, system settings, credential stores or external repos except already-authorized task-specific resources.

## 5. Current software architecture

Use software/python and software/web canonical source and test manifests. Plasma Gateway uses standard-library HTTP + REST polling; it is not FastAPI/WebSocket. Do not invent implicit Gateway endpoints, switch network ports or assume a central fleet scheduler. Inspect current source before changing APIs or protocol.

## 6. Python environment and domain rules

Python supports 3.11+; use the repo's actual development environment. Keep Protocol v3.3 and Web REST v3 identity canonical. Never equate a generated image, target description or host-only OpenOCD config with qualified real programming support. Check relevant source/tests and the detailed rules before modifying those domains.

## 7. Web environment

Use the actual Web package.json, scripts and components; do not assume a framework. Apply Web REST v3 and normalized execution semantics; run affected lint/unit/build validation. Frontend simulation does not prove PPU Runtime or FPGA hardware.

## 8. Runtime services and ports

Read scripts/plasmactl and runtime configuration before changing any service or port. Plasma Gateway integration endpoint normally uses port 18080; some code-level defaults differ. Desired configuration persistence is not Runtime activation. No unapproved activation, restart, service/network exposure or production deployment.

## 9. Site execution invariants

Sites remain independent except genuine common hardware/resource synchronization. Per-Site cancellation must not cancel unrelated Sites. Batch cancellation retains authoritative batch classification while preserving truthful final Job outcome. Program is write-only. A common Normalized Image lease may synchronize Sites when one PPU shares the execution image.

## 10. Service and process safety

Identify exact PIDs/service owners before stopping processes. Never use broad pkill/killall by language/runtime name; do not stop unrelated host services, networking, SSH or storage. Never expose internal ports to untrusted networks to bypass connectivity problems.

## 11. Autonomous task execution contract

### 11.1 Exact two-gate workflow

1. Before any new code/config/docs/PR/host or hardware modification, inspect read-only, present the bounded Plan and Path, and obtain explicit **Gate 1** approval.
2. Execute the authorized scope independently through actual acceptance (including real SWPC/Z2 only if included). Record real output/exit/status; diagnose, fix and retest in the same Gate 1. A missing capability is NOT_RUN, not PASS.
3. Prepare branch and PR with required CI, Ruleset/Review/Thread and evidence. Move Draft -> Ready when complete; no intermediate human approval gate.
4. Obtain explicit **Gate 2** approval for a specific PR and HEAD, then recheck live GitHub state and use authorized merge method. Confirm Merge SHA, both Parents and Git Tree.
5. Post-merge deployment or physical operations proceed only if explicitly covered by Gate 1; otherwise request revised Gate 1. Never treat merge as permission to deploy.

### 11.1A Clickable owner approval choices (normative UX; no new gate)

Use up to four explicit scoped choices when appropriate, but buttons do not themselves create new gates. Present only the currently applicable Gate and never ask twice after explicit owner approval. Gate 2 merge choice only when PR is merge-ready. Non-approval choices do not authorize implementation or merge.

### 11.1B Three-Path Work Execution Model (normative)

- Path 1: ChatGPT Direct Work -> GitHub PR -> GitHub-hosted CI; for software/docs/Host-only engineering.
- Path 2: existing GitHub Actions -> authorized SWPC fixed CLI -> real exit/evidence, when deterministic commands suffice.
- Path 3: existing GitHub Actions -> authorized SWPC-plasma-codex Runner -> rootless USB/TTY-visible Codex CLI autonomous work -> trusted worker commits fixes to the exact authorized PR -> authentic evidence and CI. In the owner-approved Gate 1 scope Codex may operate Z2 through the enrolled SSH/sudo route; device visibility alone does not waive physical safety.
- Path choice belongs to Gate 1. **No silent route fallback**, no simulated or assumed GitHub Dispatch, no unintended SWPC activity or privilege bypass. Path 2 retains its protected executor. Path 3 may use enrolled Z2 SSH/sudo for approved privileged development and FPGA operations, subject to actual Linux access, safe image identity, device ownership and Golden Restore.
- The detailed Three-Path design is in [docs/development/plasma-three-path-execution-model.md](docs/development/plasma-three-path-execution-model.md).

### 11.2 Routine autonomous work after Gate 1

Do not repeatedly seek confirmation for ordinary in-scope edits, builds, CI repairs or polling. Avoid redundant comprehensive readiness reviews for unchanged SHA. Stop only on material scope expansion, real access/safety blocker or Gate 2 merge decision.

## 12. Scope coverage and escalation — no third gate

Explicit Gate 1 scope is required for runtime/deployment/restart/network configuration, physical power/voltage/FPGA/IC programming, destructive or history-rewriting Git operations, and material architecture or security changes. No force-push, rebase of shared history, git reset --hard or git clean that can discard user work without such scope. Merge to main always requires Gate 2.

## 13. Merge-ready definition

Implementation and diff reviewed; applicable tests/CI PASS; no blocking Rulesets/Reviews/unresolved Threads; exact HEAD and base verified; mergeability confirmed; real required SWPC/hardware evidence available or explicitly deferred by owner. No invented PASS claims. Then Ready for Review and Gate 2, not an automatic merge.

## 14. Git publication policy

Use feature branch and PR, preserve other contributors' changes. No direct feature commits to main, no force-push or history rewrite for aesthetics. Confirm HEAD, branch, worktree and target main before edits. Verify merge commit SHA/Parents/Tree after owner Gate 2.

## 15. Validation policy

Development Mode uses the minimum sufficient authentic experiment. Stop after one complete PASS; only FAIL or insufficient evidence warrants targeted diagnosis, repair and retest. Program/Readback/Verify have no numerical retry quota; this is not permission for uncontrolled loops or unsafe repeats. Never automatically repeat an operation after uncertain electrical state, unreaped process or uncertain recovery. Run smallest focused tests first and full relevant CI before readiness. Python and PL source tests, Web lint/test/artifact checks, cross-stack integration and physical HIL are distinct layers; a lower layer does not certify a higher one. Never infer hardware acceptance from hosted mocks.

## 16. FPGA / PL rules

For pl/ or hardware-visible changes read pl/AGENTS.md and the FPGA development/verification guides. Production RTL uses SystemVerilog and canonical Site naming. Validate CDC/reset/clock/XDC/register maps, PS/PYNQ access, simulation/lint/SVA/cocotb as applicable. Claim synthesis, timing, BIT/HWH and real Z2 outcomes only when executed and observed.

## 17. Z2 production direction

Z2 is an embedded PPU, not a clone of the workstation. Do not transplant developer tools, credentials or build-time infrastructure into the runtime by default. Check PYNQ/XRT compatibility before standardizing runtime dependencies.

## 18. Current known boundaries / technical debt

Preserve current implementation limits: Python >=3.11; integration Gateway normally port 18080; REST polling; canonical-only Protocol v3.3 and Web REST v3; not every declared Programming Asset type is implemented; Recipe/Package remains evolving; fleet Manager is not unrestricted proxy/scheduler; Desired persistence does not mean activation; SWPC mock does not certify DUT programming. Consult [detailed contract](docs/development/plasma-autonomous-development-contract-full.md) before advancing unsupported features.

## 19. Communication and completion report

Report exact checked SHA and execution Path, real executor/Runner, run/job ID where applicable, observed result, blocked/not-run operations, changed files, tests and CI, outstanding safety/recovery concerns, and next Gate. Be concise; never portray intended tests as completed.

## 20. Workspace and information boundary

Do not read or publish private prompts, SSH credentials, API tokens, raw Codex Session transcripts, operator home directories or other unrelated files. The owner may explicitly authorize a bounded resource for a task; redact any sensitive output and honor actual permissions. The existing protected Z2 Root operation/transport and B1/B2/B3 ownership/restoration checks are authoritative for authorized hardware work. No hardware access without approved scope.

**On-demand contract routing:** For a narrowly scoped task, read the relevant section(s) of [the complete detailed contract](docs/development/plasma-autonomous-development-contract-full.md) and affected nested AGENTS.md files; do not preload all 62 KiB without technical need. Root AGENTS.md is concise to fit the default Codex project instruction budget; this does **not** relax any full-contract constraint.
