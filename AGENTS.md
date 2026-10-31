# Plasma Autonomous Development Contract

This is PLASMA's **primary operating contract** and the **compact Codex instruction entrypoint**. Read it before any code, configuration, documentation, deployment or hardware change. The [shared detailed contract](docs/development/plasma-development-common.md) remains normative and is incorporated by reference. Read **relevant sections on demand**, not the entire contract for unrelated tasks. Load [Path 2 CLI](docs/development/plasma-path2-cli.md) only for SWPC CLI execution or [Path 3 Codex](docs/development/plasma-path3-codex.md) only for SWPC Codex execution. ChatGPT Direct is the unnumbered default; do not renumber historical Path 2/3 identifiers. If an operation touches privileges, electrical safety, deployment, Git history or architecture, read the matching detailed clauses before acting. An abbreviated instruction never grants permissions that the full contract or an executable guard denies. For Path 2 privileged Z2 FPGA Manager/MMIO operations, retain the existing Protected Root Entry (`scripts/z2/plasma-path2-root-entry`), which validates `operation + source_sha` and invokes the reviewed `pl.hil.fpga_image_root` implementation. Path 3 may perform owner-approved Z2 SSH/sudo development deployment and FPGA operations via the enrolled credential route with real Linux privileges and hardware ownership/recovery checks; no new Stage or intermediate approval is required.

**Exactly two owner approval gates:** Gate 1 — Plan Approval *before any new implementation*; Gate 2 — Merge Approval for a specific merge-ready PR. No third gate for Ready, hardware, runtime or deployment. Once Gate 1 is approved, autonomously complete all in-scope work and actual acceptance, including fixes and CI; do not request repeated approval. Material scope change requires a revised Gate 1. **Never merge without Gate 2.**

**Default mode: DEVELOPMENT MODE — owner-operated prototype.** Optimize Build -> Run -> Observe -> Fix and the smallest meaningful real result, not ceremonies or production/fleet policy. This does not remove electrical, OS permission, hardware ownership or recovery guards. PASS/FAIL/NOT_RUN must correspond to observed execution.

## 1. Project purpose and canonical domain

PLASMA is a configurable, multi-Site IC programmer; PYNQ-Z2 is the prototype target. Hierarchy: Facility -> PPU -> SITE 1..N (one-based site_id = 1..N); Socket is a fixture, not Site identity. PPU exposes the **Plasma Gateway** service, its **Plasma Gateway API** and **Plasma Gateway Endpoint**. The Linux **Default Gateway** is an unrelated layer-3 next-hop; do not conflate them. The canonical Protocol v3.3 uses PLASMA33 and site_id 1..N; Web REST contract v3 is canonical. **Plasma Manager** implements bounded managed PPU command routing, not a central universal scheduler. Programming Asset is input; Normalized Image is the execution model. Never reintroduce retired zero-based Channel/Programmer identity into production paths.

Repository: pl/ FPGA and verification; software/python/ embedded/control/REST; software/web/ Console; scripts/ integration and orchestration; docs/ design and operation.

**Hardware execution boundary (normative; CI-enforced):** In the deployed PLASMA system, **SWPC runs Web / Controller / BFF** and sends high-level commands/status over Ethernet; **Z2 PS runs the embedded Linux programming runtime, including the OpenOCD process and its PS-local WordPort/Remote Bitbang bridge**; **Z2 PL executes FPGA SWD/SPI hardware I/O to the DUT**. SWPC may build, package, simulate or host-only test OpenOCD for development but must not run the live programmer backend or forward per-bit SWD traffic to Z2 as the product/physical-PoC path. Paths 2/3 on SWPC are development execution routes, not product OpenOCD hosts. The [PS OpenOCD architecture](docs/architecture/ic-support-openocd-plan-executor.md) is a mandatory code/PR/CI boundary: a change to execution location requires an explicit revised Gate 1 architecture decision and a synchronized architecture contract, implementation and CI test. Keep this invariant separate from production hardware-qualification claims.

### Z2 Blue Pill SWD — select the current physical route

For external Blue Pill SWD, the sole current route is Z2 PS-local ARMv7 OpenOCD -> UNIX WordPort/RemoteBitbang (`scripts/bluepill-wordport-session.py`) -> paired PL SWD Image/Manifest (`pl/projects/z2-bluepill-rbb/image-manifest.json`) -> PMOD SWCLK/SWDIO. SWPC is not the live OpenOCD host. Before real hardware work check current boot, source, image identity, Root/FPGA ownership, recovery and voltage; historical CI or DPIDR never substitutes for a real observation. **Do not select retired** `z2-swd-gpio`, `z2-swd03-axi` or standalone SWD-04/05 HIL entrypoints. Keep imported Root/recovery helpers intact. Details and exclusions: [SWD retirement contract](docs/development/swd-legacy-path-retirement.md), [OpenOCD architecture](docs/architecture/ic-support-openocd-plan-executor.md).

## 1A. Prototype-first engineering policy (normative)

Prototype outcomes require the smallest authentic build/test/HIL result. Hosted mocks never prove SWPC, FPGA load, Z2, DUT, voltage or real IC programming. Reuse prior valid board enrollment, identity, artifacts and recovery evidence when applicable, but check current ownership, permissions, candidate identity and actual hazard conditions. Default Z2 internal-loopback HIL to the existing development profile when that HIL is explicitly authorized; qualification profile is only for deliberate qualification.

For healthy normal development aim for at most 180 seconds of pre-experiment checks; this is an objective, **not** permission to omit real safeguards. Preserve legal voltages, current PL/MMIO ownership, artifact identity, rollback image and recovery. Stop on actual SIGBUS, conflicting drivers, dangerous power/voltage, missing root authority or uncertain restoration. Never equate a file hash or CI green check with physical safety.

### FPGA PS/PL Image pairing and Keep Loaded (normative)

Deliver each FPGA BIN with its companion Manifest. Protected Root validates BIN SHA256, board/part, ABI, current ownership and recovery; Root source pin protects executable code, **not** individual Image data. Do not add per-Image approval tokens, fixed release allowlists, `runtime_admitted` or Root source changes for each Image. Manifest is consistency evidence, not publisher authentication.

Allow direct safe Image A -> Image B replacement without routine Golden reload. After a **proven successful FPGA Download**, Keep Loaded by default even if downstream MMIO/DPIDR fails; functional FAIL is not itself a restore trigger. Stop SWD/DUT activity and reap processes/release leases safely on test failure. For failed load, UNKNOWN/unsafe/in-flight state, electrical hazards or unreaped owner, **fail closed**; preserve verified Golden and invoke Restore only for explicit or documented recovery, never blindly. Detailed preconditions and recovery policy: [shared FPGA/Z2 contract](docs/development/plasma-development-common.md).

### 1A.1 Development Mode — choose Path, then read its rules (normative)

- Use the existing Work Order, Dispatcher, Runner and native tools. Do not introduce a third approval gate or task-specific middleware.
- Default: ChatGPT Direct for code, docs and Host-only CI (formerly Path 1; no separate path selection).
- **Path 2:** deterministic SWPC CLI, CPU-only tasks, operator CLI and Vivado builds. **When Path 2 is selected, read [Path 2 execution contract](docs/development/plasma-path2-cli.md) and the applicable [existing operational rules](docs/development/plasma-codex-path2-execution.md).**
- **Path 3:** SWPC Codex CLI for autonomous diagnosis/repair and approved hardware tasks. **When Path 3 is selected, read [Path 3 execution contract](docs/development/plasma-path3-codex.md) and the applicable [existing operational rules](docs/development/plasma-codex-path3-execution.md).**
- Select the smallest capable Path. Path 2 and Path 3 may share the existing Runner; do not invent extra isolation or fixed-operation middleware without demonstrated need.
- Preserve exact Owner/Gate 1 scope, SHA/digest binding, actual Linux privileges, applicable Root Guard, hardware ownership, electrical safety, recovery and authentic evidence. Choosing a Path never grants additional authority.
- For an unchanged PR HEAD, avoid repeating full readiness reviews; before an authorized Gate 2 merge verify live HEAD/main, necessary CI, Rulesets, Reviews, Threads, dependencies and Mergeability.
- If approved work requires real SWPC acceptance, GitHub-hosted mocks are not physical evidence. Record actual Run/Job, exit, hashes and recovery; do not merge untested changes merely to trigger a main-only dispatcher.
- No unapproved deployment, destructive Git, privilege escalation, device operation or credential disclosure. Material scope expansion requires revised Gate 1.

## 1B. SSH/sudo and Codex execution boundary

An approved Gate 1 is an execution assignment, not a new planning gate. Path 3 may use the enrolled SSH/sudo route only with actual privileges and authorized scope; credentials remain in the private owner-controlled store, never in commits/logs/artifacts. No sudoers modification, privilege bypass or invented Z2 state. For real FPGA/HIL work, follow [shared Z2 Root/recovery constraints](docs/development/plasma-development-common.md) and [Path 3 execution contract](docs/development/plasma-path3-codex.md).

## 2–10. Domain and execution contracts (load on demand)

- **Programming semantics:** Site identity is one-based; Program writes only; Erase/Verify/Read are distinct operations. Asset input and Normalized Image execution identity are not interchangeable. Site cancellation must not cancel unrelated Sites; synchronize only genuinely shared resources. Read [shared data model and Site invariants](docs/development/plasma-development-common.md) and domain tests before edits.
- **Interrupt isolation:** Before destructive Erase/Program on interrupt-capable MCUs, qualify target quiescence/interrupt isolation per exact ICPN/Provider. Unknown isolation fails closed; do not blindly apply Cortex-M `maskisr` to other families. See [programming interrupt isolation policy](docs/architecture/programming-interrupt-isolation-policy.md); non-STM32 enforcement is not assumed implemented.
- **Source priority:** executable code/config > `scripts/plasmactl` for host operations > package manifests > tests > current docs > historical discussions. Inspect actual implementation; never infer support from metadata or mock results.
- **Zones:** Cloud/CI is host-only evidence; SWPC is integration/build/development host; Z2 PS/PL and DUT are real hardware. Path 3 `workspace-write` is the ordinary sandbox; owner-authorized SHA/digest-bound hardware Work Orders may use `danger-full-access`, but sandbox settings do not override Linux DAC/ACL, SSH, protected Root Entry, or safety checks. Do not inspect unrelated user files.
- **Architecture/runtime:** SWPC Web/Controller/BFF, Z2 PS live OpenOCD and bridge, Z2 PL SWD/SPI; Gateway is standard-library HTTP/REST polling, not FastAPI/WebSocket. Read current source, `scripts/plasmactl`, and the [shared architecture/runtime clauses](docs/development/plasma-development-common.md) before changes. Gateway integration commonly uses port 18080; no unapproved service restart, port exposure or deployment. Desired persistence does not mean activation.
- **Process safety:** identify precise service/PIDs before stopping; no broad `pkill`/`killall` or disruption of unrelated SSH, network or storage services.

## 11. Autonomous task execution contract

### 11.1 Exact two-gate workflow

1. Before any new code/config/docs/PR/host or hardware modification, inspect read-only, present the bounded Plan and Path, and obtain explicit **Gate 1** approval.
2. Execute the authorized scope independently through actual acceptance (including real SWPC/Z2 only if included). Record real output/exit/status; diagnose, fix and retest in the same Gate 1. A missing capability is NOT_RUN, not PASS.
3. Prepare branch and PR with required CI, Ruleset/Review/Thread and evidence. Move Draft -> Ready when complete; no intermediate human approval gate.
4. Obtain explicit **Gate 2** approval for a specific PR and HEAD, then recheck live GitHub state and use authorized merge method. Confirm Merge SHA, both Parents and Git Tree.
5. Post-merge deployment or physical operations proceed only if explicitly covered by Gate 1; otherwise request revised Gate 1. Never treat merge as permission to deploy.

### 11.1A Clickable owner approval choices (normative UX; no new gate)

Use up to four explicit scoped choices when appropriate, but buttons do not themselves create new gates. Present only the currently applicable Gate and never ask twice after explicit owner approval. Gate 2 merge choice only when PR is merge-ready. Non-approval choices do not authorize implementation or merge.

### 11.1B Execution Routing (normative)

- Default (unnumbered): ChatGPT Direct -> GitHub PR -> GitHub-hosted CI for software/docs/Host-only engineering.
- Path 2: existing GitHub Actions -> authorized SWPC fixed CLI -> real exit/evidence, when deterministic commands suffice.
- Path 3: existing GitHub Actions -> authorized SWPC-plasma-codex Runner -> rootless USB/TTY-visible Codex CLI autonomous work -> trusted worker commits fixes to the exact authorized PR -> authentic evidence and CI. In the owner-approved Gate 1 scope Codex may operate Z2 through the enrolled SSH/sudo route; device visibility alone does not waive physical safety.
- Path choice belongs to Gate 1. **No silent route fallback**, no simulated or assumed GitHub Dispatch, no unintended SWPC activity or privilege bypass. Path 2 retains its protected executor. Path 3 may use enrolled Z2 SSH/sudo for approved privileged development and FPGA operations, subject to actual Linux access, safe image identity, device ownership and Golden Restore.
- The historical execution-route design is in [docs/development/plasma-three-path-execution-model.md](docs/development/plasma-three-path-execution-model.md).

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

## 17–18. Production direction and known limits

Z2 is an embedded PPU, not a development workstation: do not copy build tools or credentials into runtime by default. Do not claim unsupported ICs, Asset formats, fleet functions, activation or real DUT qualification. Consult [shared contract](docs/development/plasma-development-common.md) and current source for actual limitations.

## 19. Communication and completion report

Report exact checked SHA and execution Path, real executor/Runner, run/job ID where applicable, observed result, blocked/not-run operations, changed files, tests and CI, outstanding safety/recovery concerns, and next Gate. Be concise; never portray intended tests as completed.

## 20. Workspace and information boundary

Do not read or publish private prompts, SSH credentials, API tokens, raw Codex Session transcripts, operator home directories or other unrelated files. The owner may explicitly authorize a bounded resource for a task; redact any sensitive output and honor actual permissions. The existing protected Z2 Root operation/transport and B1/B2/B3 ownership/restoration checks are authoritative for authorized hardware work. No hardware access without approved scope.

**On-demand contract routing:** For a narrowly scoped task, read the relevant section(s) of [the relevant shared contract sections](docs/development/plasma-development-common.md) and affected nested AGENTS.md files; do not preload the full shared contract without technical need. Root AGENTS.md is concise to fit the default Codex project instruction budget; this does **not** relax any full-contract constraint.
