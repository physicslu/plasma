# Plasma Autonomous Development Contract

This is PLASMA's **primary operating contract** and the **compact Codex instruction entrypoint**. Read it before any code, configuration, documentation, deployment or hardware change. Load detailed contracts **on demand** only for the scopes you actually touch.

- Shared detailed clauses: [plasma-development-common.md](docs/development/plasma-development-common.md)
- Path 2 (SWPC CLI): [plasma-path2-cli.md](docs/development/plasma-path2-cli.md)
- Path 3 (SWPC Codex): [plasma-path3-codex.md](docs/development/plasma-path3-codex.md)
- Domain contracts: see routing table below

An abbreviated instruction never grants permissions that the full contract or an executable guard denies. ChatGPT Direct is the unnumbered default; do not renumber historical Path 2/3 identifiers.

**Exactly two owner approval gates:**
- **Gate 1** — Plan Approval *before any new implementation*
- **Gate 2** — Merge Approval for a specific merge-ready PR

No third gate for Ready, hardware, runtime or deployment. Once Gate 1 is approved, autonomously complete all in-scope work and actual acceptance (including fixes and CI). Material scope change requires a revised Gate 1. **Never merge without Gate 2.**

**Default mode: DEVELOPMENT MODE — owner-operated prototype.** Optimize Build → Run → Observe → Fix and the smallest meaningful real result. This does not remove electrical, OS permission, hardware ownership or recovery guards. PASS/FAIL/NOT_RUN must correspond to observed execution.

**Development priority — EFFICIENCY FIRST, essential safety always (normative).** In owner-operated prototype development, optimize for the shortest safe path to an observed functional result, not maximum preflight coverage or production-style qualification. Reuse qualified evidence and prefer existing commands, focused delta checks, bounded experiments and rapid Build → Run → Observe → Fix. **Apply only safeguards tied to a concrete relevant hazard or invariant** (electrical/power safety, OS/device ownership, resource isolation, durable state and UNKNOWN/no-blind-resend); do not waive them to gain speed. Any proposed additional test, stop or prerequisite must identify the actual risk and use the least burdensome effective mitigation. Defer unrelated, speculative or production-only checks as NOT_RUN/NOT_VERIFIED without blocking otherwise authorised development. Where a small reversible experiment can safely answer the question, prefer it to another broad audit.

## Development autonomy and restriction provenance (normative)

- **Do not invent restrictions.** Do not add unrequested approval steps, blanket deployment/FPGA/Site bans, arbitrary test limits or production-grade prerequisites without a basis in the owner-approved Gate 1, applicable repository contracts, executable guards or demonstrated engineering safety. Missing evidence is NOT_VERIFIED, not proof of failure or an automatic ban on unrelated safe work.
- **Execute the approved scope end-to-end.** After Gate 1, autonomously perform necessary in-scope configuration, code/RTL changes, testing, diagnosis, deployment/restarts, resource activation and hardware work **when those operations are included in the authorization**. Do not subdivide approved work into repeated owner approvals. Actual OS privileges, resource locks, electrical safety and recovery guards remain binding.
- **Separate development from production.** Do not silently impose future factory/fleet/production controls on a development experiment. Honor owner-approved development exceptions within their exact scope, and report excluded validation as NOT_RUN or NOT_VERIFIED; never claim production qualification, Power Control or electrical SAFE_OFF without physical evidence.
- **Explain real blockers.** For any new restriction or stop condition, state its precise source (owner decision, repository contract, live configuration, executable guard or physical hazard), observed evidence, material risk and least-restrictive safe resolution. Distinguish a temporary configuration gap from a policy prohibition. Ask the owner only when facts cannot be established safely or a material scope change requires a revised Gate 1.
- **Preserve two Gates and task-specific limits.** Gate 1 authorizes the bounded work; Gate 2 alone authorizes PR merge. Do not introduce a third Gate or re-request granted permission. Task-specific Flash quotas, hardware permissions and experimental exceptions must not become global defaults.
- **Do not bypass real protections.** Preserve electrical safety, exact target/route admission, Site ownership, transaction consistency, OUTCOME_UNKNOWN no-blind-resend, recovery and truthful evidence. Development autonomy removes redundant human checkpoints, not technical safety controls.

**PPU Bundle v3 (PR #1225):** Canonical deployment hierarchy is **Bundle → Packages → Files**: `plasma.ppu.bundle.v3`, manifest `packages[]` (1–32), `payload/packages/<package-id>/...`, with package `id`, `kind`, `version`, `requires`, `files`. Retired Bundle v2 `components` and Package v1 are not new accepted wire formats; do not confuse these with legitimate FPGA/UI components. See [Bundle v3 contract](docs/architecture/ppu-canonical-bundle-packages.md) and [Target Platform Identity proposal](docs/architecture/ppu-target-platform-identity.md). This does not authorize deployment, FPGA/DUT operation, or bypass Gate 2.

## Project purpose and hard boundaries

PLASMA is a configurable, multi-Site IC programmer; **PPU means Plasma Programming Unit** (the hardware product identity), while PYNQ-Z2 is only the current prototype board. Keep product-wide tools named for PPU and reserve Z2 names for board-specific drivers, installers and enrollment details. Hierarchy: Facility → PPU → SITE 1..N (one-based `site_id`). Socket is a fixture, not Site identity. Protocol v3.3 (PLASMA33) and Web REST v3 are canonical. PPU exposes the **Plasma Gateway** service, its **Plasma Gateway API** and **Plasma Gateway Endpoint**. The Linux **Default Gateway** is an unrelated layer-3 next-hop; do not conflate them. Plasma Manager provides bounded managed PPU routing, not a universal scheduler. Programming Asset is input; Normalized Image is the execution model. Never reintroduce retired zero-based Channel/Programmer identity.

**Hardware execution boundary (normative; CI-enforced):**
- **SWPC runs Web / Controller / BFF** and sends high-level commands over Ethernet.
- **Z2 PS runs the embedded Linux programming runtime**, including the live OpenOCD process and its PS-local WordPort/Remote Bitbang bridge.
- **Z2 PL** executes FPGA SWD/SPI hardware I/O to the DUT.

SWPC may build/test OpenOCD offline but must **not** host live OpenOCD or forward per-bit SWD traffic as the product path. Changing this placement requires an explicit revised Gate 1 architecture decision plus synchronized contract, implementation and CI. See [OpenOCD architecture](docs/architecture/ic-support-openocd-plan-executor.md).

**ST-LINK control group (owner-approved 2026-11-15):** an ST-LINK attached to SWPC may run OpenOCD against a DUT as an independent verification control group (for example, reading DPIDR to separate a DUT fault from a Z2/PL/wiring fault). It is not the product path, and its result is never Site, Z2 or E/P/V evidence. It may stay wired alongside the Z2 PMOD; the operator must not drive both at the same time.

**Current Z2 Blue Pill physical SWD path (normative):** Z2 PS-local OpenOCD `plasma_swd` adapter → paired PL ABI-v5 SWD engine image → PMOD (WordPort/Remote Bitbang is kept only as an experiment/comparison path). Do not select retired SWD entrypoints. Details: [SWD retirement](docs/development/swd-legacy-path-retirement.md) and the FPGA / Embedded contracts.

## Domain contract routing (normative)

Load [Common](docs/development/plasma-development-common.md) and **only** the applicable domain contracts according to the actual changed interfaces (not according to the execution Path):

| Changed scope | Required domain contract | Also load when interfaces affected |
| --- | --- | --- |
| FPGA RTL / XDC / PL image / MMIO | [FPGA](docs/development/plasma-fpga.md) | [Embedded](docs/development/plasma-embedded.md) for PS-facing ABI |
| Z2 Linux / OpenOCD / PS driver | [Embedded](docs/development/plasma-embedded.md) | [FPGA](docs/development/plasma-fpga.md) for PL ABI |
| Manager / Gateway / backend REST | [Manager](docs/development/plasma-manager.md) | [Embedded](docs/development/plasma-embedded.md) or [Web](docs/development/plasma-web.md) |
| Web UI / frontend | [Web](docs/development/plasma-web.md) | [Manager](docs/development/plasma-manager.md) for changed REST APIs |
| Cross-layer API / protocol | Common + every affected domain | Validate producers and consumers |

Path 2 / Path 3 are selected independently of domain. Skipping unrelated documents never waives interface compatibility, Root Guard, Gate approvals, hardware ownership, electrical safety or evidence requirements.

### Path selection (normative)

- Default: ChatGPT Direct (code, docs, host-only CI).
- **Path 2**: deterministic SWPC CLI / CPU-only / operator CLI / Vivado. When selected, read [Path 2 contract](docs/development/plasma-path2-cli.md).
- **Path 3**: SWPC Codex for autonomous diagnosis/repair and approved hardware tasks. When selected, read [Path 3 contract](docs/development/plasma-path3-codex.md). Ordinary Path 3 explicitly pins `--sandbox workspace-write`. **Do not apply retired Issue #981 read-only Pilot or no-hardware Runner restrictions to current Path 3.** Owner-approved, SHA-pinned guarded-hardware Work Orders may use native SSH/USB/TTY and DUT tests under verified Linux DAC/ACL, device ownership and Root safety checks; historical Runner UID or a sandbox mode alone proves neither permission nor prohibition.

Select the smallest capable Path. Choosing a Path never grants additional authority beyond the approved Gate 1 scope, actual Linux privileges, Root Guard and safety checks.

## Core engineering policies

**Delta Verification / reuse accepted evidence (normative; ChatGPT Direct, Path 2, Path 3)**

- **Start from the last accepted baseline, not from zero.** For each request, identify the actual source/config/interface/hardware delta and the specific new outcome. Reuse prior observed PASS, approved Gates and immutable evidence when their tested conditions still apply. Do not restart a repository-wide architecture/ADR/PR/CI audit or ask the owner to restate known decisions merely because a new task begins.
- **Verify the affected surface only.** Execute the smallest relevant functional check, boundary/negative regression and applicable safety guard for the delta. Expand only when a material dependency changed, evidence no longer covers the requested behavior, an observed failure points outside the initial scope, or an executable policy explicitly requires it. A checklist is not evidence that every item must be rerun.
- **Preserve evidence type and validity.** Confirm only the baseline identity and conditions needed for reuse (e.g. exact source/test SHA, changed dependencies, runtime configuration and hardware mapping). Hosted CI/Mock PASS is reusable software evidence, never a substitute for new physical HIL. A materially changed source requires the relevant new tests and the required exact-HEAD CI/merge checks; unchanged historical checks do not become new work.
- **Do not manufacture approval gates or blanket prohibitions.** An already approved Gate 1 covers its bounded work; Gate 2 still governs PR merge. Distinguish legitimate safety checks before an authorized hardware operation from fresh owner approval, speculative factory prerequisites and unrelated full requalification.
- **Example — WP-01 after #1439/#1441 merge:** Retain accepted architecture and Hosted CI evidence; the next unsolved question is whether the real Z2 PPU can run its two installed Sites concurrently. Check effective PPU concurrency and shared electrical/FPGA ownership, then prove two real overlapping Flash/Verify executions with independent Job/Receipt and safe outcomes under an authorized HIL scope. Do **not** redo all single-Site or 8-Site Host-only work just to start 2-Site qualification.
- **Report the delta, not a recycled audit.** Summarize (1) reused evidence, (2) new checks actually run and their PASS/FAIL/NOT_RUN, (3) specific unresolved blockers and next action. Never represent a prior PASS as a new execution, or omit a necessary safety check in the name of efficiency.

**Engineering simplicity and scope control (normative; no new Gate)**

1. **Existing First — execute before expanding.** For an approved bounded task, use the existing canonical command/API and current proven route first. Do not add a wrapper, service, architecture layer or new implementation without a specific demonstrated gap. Respect existing admission, authorization and physical safety guards.
2. **Minimal Scope — solve only the requested problem.** Keep implementation and verification limited to the requested outcome and its necessary dependencies. Do not turn one-Site/one-Flash work into unsolicited A/B/A, burn-in, multi-Site Scheduler changes, CDC qualification, deployment, or broad re-audits. Distinguish required Flash safety from optional post-Flash observations.
3. **One Task, One Result — no silent amplification.** A request for one Flash authorizes at most one intended programming attempt, not extra repetitions or automatic retries. Record the real Job/Receipt and report PASS, FAIL, BLOCKED or NOT_RUN. If submission outcome is unknown, reconcile it; never blindly resubmit.
4. **Evidence Before Code — diagnose the actual failure.** Inspect the existing implementation and observed error before modifying code. A successful workflow/Codex exit is not a substitute for the requested functional or physical result. Fix the smallest evidence-backed cause, then run the relevant focused regression and safety checks; do not claim unrun checks as PASS.
5. **Complexity Budget — default to zero new files.** Prefer simplifying or deleting duplicate paths over adding abstractions. For engineering changes, report added LOC, removed LOC, net LOC, new files and why each addition was necessary. Zero new files is the default target, not an excuse to omit necessary tests or safety fixes.

These rules apply to ChatGPT Direct, Path 2 and Path 3. They do not add approval gates, weaken safety/transaction guarantees, or override the exact owner-approved task scope.

**Replace-by-Default.** New versions replace old versions directly across API, Schema, Protocol, Package, FPGA IP, Driver and tools. Migrate dependents (implementation, callers, tests, docs, CI) in the same change. Do not keep Compatibility Layers or dual-track architectures merely for old tests. Exceptions require explicit owner approval.

**Anti-Resurrection (normative; enforce Replace-by-Default).** A deliberate deletion remains a constraint across new files, workflows and deployment paths: before restoring a removed component, compatibility branch, static version allowlist or build dependency, inspect the merged removal decision and current callers, and prove why the existing canonical route cannot serve the need. Renaming or relocating the retired behavior does not make it new. Do **not** silently restore `ppu-z2-installer-core.py` as a shipped/installed executable path (#1433), Bundle-side Engine/Admission SHA version pins (#1329), or Python Admission changes as an OpenOCD *binary compilation* trigger; preserve source-appropriate Host-only validation instead. Per-artifact SHA256 integrity, selected Engine/Root ownership, driver ABI, exact-source evidence and safety interlocks remain required and must **not** be mistaken for forbidden static update-version allowlists. A bounded one-shot maintenance tool is not a precedent for a generic deployment policy. Any genuine old-device migration exception needs explicit owner approval and a removal boundary; reject disguised permanent compatibility. Keep focused negative regression coverage in existing tests/CI; no new gate or duplicate policy system.

**Source priority:** executable code/config > `plasmactl` (`utilities/plasmactl/`) > package manifests > tests > current docs > historical discussion. Inspect actual implementation; never infer support from metadata or mocks.

**Operator CLI (`plasmactl`).** One CLI, canonical source [`utilities/plasmactl/`](utilities/plasmactl/README.md) (Python 3.10-compatible, Path 2/3- and Runner-neutral); `scripts/plasmactl` is only its repository launcher, also shipped in the Z2 PS kit. Programming uses `plasmactl program` over the existing Manager Batch API: one start ID and one Batch per submission, a new `--journal` per submission, and on `OUTCOME_UNKNOWN` reconcile read-only (`program reconcile`), never resend. `install/deploy/verify/status/logs/restart` delegate to the existing profile backends in `utilities/plasmactl/backends/`, which own platform, systemd, Root Guard and rollback. `scripts/plasma_program.py` is single-PPU Bundle commissioning (B1–B3, Runtime Kit), not a production programming entry. Extend this CLI instead of adding parallel CLIs, wrappers or one-off runners; the retired Path 2 load benchmark and `p2hw-*` claim (#1485) stay retired.

**Evidence:** Hosted CI / mocks never prove Z2, FPGA load, DUT, voltage or real IC programming. Record authentic PASS / FAIL / NOT_RUN. Keep Loaded after proven successful FPGA Download is the default; functional FAIL alone is not a Golden Restore trigger. Details live in the FPGA and Embedded contracts.

**Process safety:** Identify precise service/PIDs before stopping. No broad `pkill`/`killall`. No unapproved deployment, destructive Git, privilege escalation or credential disclosure.

## Codex token efficiency (advisory; no new Gate)

- Minimize **model round-trips and context size** together. Follow the domain routing above; bound searches and file/CI output to relevant excerpts, and do not repeatedly read unchanged files without a new reason.
- Batch independent read-only inspections when safe; keep dependent edits, failures and verification visible. Reuse evidence for unchanged HEAD, but run all required focused, regression, negative and safety checks for the approved scope.
- For CI, prefer a single bounded status collection and asynchronous waiting over repeated model-driven polling. Fetch detailed logs for failed or ambiguous jobs; do not recheck unchanged successful results without cause.
- For small/medium host-only tasks, review tool churn and remaining acceptance at about **20 top-level tool calls**; at about **35**, record a concise efficiency checkpoint and reduce redundant work. These are **advisory checkpoints**, not stop conditions, test limits, approval gates or permission to leave Gate 1 incomplete.
- Continue the approved Build → Run → Observe → Fix → Retest loop to observed PASS or an actionable blocker. Safety, recovery, interface compatibility and Gate evidence take precedence over token savings; only a material scope change requires revised Gate 1.
- When metrics are available, report model/effort, tool calls and cached/non-cached/output tokens as observed. Do not infer five-hour subscription allowance consumption from local token counters. Stop nonessential inspection after required Gate readiness evidence is complete.

## Approval, Git and completion

Gate 1 = bounded plan before implementation. After approval, finish all in-scope work autonomously. Gate 2 = explicit merge approval for a specific merge-ready PR (verify HEAD, CI, Rulesets, Reviews, Threads, Mergeability). Merge does not authorize deployment or hardware operations.

Report: exact SHA, Path, executor/Runner, run/job ID (if any), observed result, blocked/not-run items, changed files, tests/CI, outstanding safety/recovery concerns, next Gate. Be concise; never portray intended tests as completed.

## Workspace boundary

Do not read or publish private prompts, SSH credentials, API tokens, raw Codex transcripts, operator home directories or unrelated files. Credentials stay in the owner-controlled private store (see Embedded contract). No hardware access without approved Gate 1 scope.

Root AGENTS.md is deliberately concise to fit the default Codex project instruction budget. This does **not** relax any constraint present in the full domain or Path contracts.

<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->
