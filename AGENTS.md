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

**PPU Bundle v3 (PR #1225):** Canonical deployment hierarchy is **Bundle → Packages → Files**: `plasma.ppu.bundle.v3`, manifest `packages[]` (1–32), `payload/packages/<package-id>/...`, with package `id`, `kind`, `version`, `requires`, `files`. Retired Bundle v2 `components` and Package v1 are not new accepted wire formats; do not confuse these with legitimate FPGA/UI components. See [Bundle v3 contract](docs/architecture/ppu-canonical-bundle-packages.md) and [Target Platform Identity proposal](docs/architecture/ppu-target-platform-identity.md). This does not authorize deployment, FPGA/DUT operation, or bypass Gate 2.

## Project purpose and hard boundaries

PLASMA is a configurable, multi-Site IC programmer; PYNQ-Z2 is the prototype target. Hierarchy: Facility → PPU → SITE 1..N (one-based `site_id`). Socket is a fixture, not Site identity. Protocol v3.3 (PLASMA33) and Web REST v3 are canonical. PPU exposes the **Plasma Gateway** service, its **Plasma Gateway API** and **Plasma Gateway Endpoint**. The Linux **Default Gateway** is an unrelated layer-3 next-hop; do not conflate them. Plasma Manager provides bounded managed PPU routing, not a universal scheduler. Programming Asset is input; Normalized Image is the execution model. Never reintroduce retired zero-based Channel/Programmer identity.

**Hardware execution boundary (normative; CI-enforced):**
- **SWPC runs Web / Controller / BFF** and sends high-level commands over Ethernet.
- **Z2 PS runs the embedded Linux programming runtime**, including the live OpenOCD process and its PS-local WordPort/Remote Bitbang bridge.
- **Z2 PL** executes FPGA SWD/SPI hardware I/O to the DUT.

SWPC may build/test OpenOCD offline but must **not** host live OpenOCD or forward per-bit SWD traffic as the product path. Changing this placement requires an explicit revised Gate 1 architecture decision plus synchronized contract, implementation and CI. See [OpenOCD architecture](docs/architecture/ic-support-openocd-plan-executor.md).

**Current Z2 Blue Pill physical SWD path (normative):** Z2 PS-local OpenOCD → WordPort → paired PL image → PMOD. Do not select retired SWD entrypoints. Details: [SWD retirement](docs/development/swd-legacy-path-retirement.md) and the FPGA / Embedded contracts.

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
- **Path 3**: SWPC Codex for autonomous diagnosis/repair and approved hardware tasks. When selected, read [Path 3 contract](docs/development/plasma-path3-codex.md). Ordinary Path 3 explicitly pins `--sandbox workspace-write`.

Select the smallest capable Path. Choosing a Path never grants additional authority beyond the approved Gate 1 scope, actual Linux privileges, Root Guard and safety checks.

## Core engineering policies

**Replace-by-Default.** New versions replace old versions directly across API, Schema, Protocol, Package, FPGA IP, Driver and tools. Migrate dependents (implementation, callers, tests, docs, CI) in the same change. Do not keep Compatibility Layers or dual-track architectures merely for old tests. Exceptions require explicit owner approval.

**Deployment transport precedence:** **Production Mode = existing Bootstrap HTTP API only** (no SSH deployment fallback). **Engineering Mode = try existing Bootstrap HTTP API first, then existing trusted SSH/SCP only when the exact API action is unavailable/unsupported, the failed transaction is known safe, and the approved scope allows it.** Record the specific HTTP failure even when SSH succeeds; never bypass admission or retry an ambiguous write. See [PPU deployment transport policy](docs/deployment/ppu-bootstrap-factory-and-hil.md#engineering-only-http-first-ssh-fallback-production-http-only).

**Source priority:** executable code/config > `scripts/plasmactl` > package manifests > tests > current docs > historical discussion. Inspect actual implementation; never infer support from metadata or mocks.

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
