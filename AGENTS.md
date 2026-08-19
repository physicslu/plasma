# Plasma Autonomous Development Contract

This file is the primary operating contract for AI coding agents working on the Plasma repository. Read it before making code, configuration, deployment, hardware, or documentation changes.

The default operating model is **goal-oriented autonomous execution with explicit approval gates**. Routine engineering work should continue without asking the user to relay shell commands or approve every intermediate step. Protected operations remain explicit human gates.

## 1. Project purpose and canonical domain

Plasma is a configurable multi-Site IC programming system. The current hardware development platform is PYNQ-Z2 (Z2).

Canonical product/domain hierarchy:

```text
Plasma System
└── Facility
    └── PPU (Plasma Programming Unit)
        ├── SITE 1
        ├── SITE 2
        └── ... SITE N
```

Definitions:

- **Facility**: deployment / administrative location.
- **PPU**: one physical Plasma programming appliance and autonomous local execution node.
- **Site**: one independently controlled Programming Site inside a PPU.
- **Socket**: mechanical/electrical IC fixture attached to a Site; it is not the Site identity.

Canonical Site identity is one-based:

```text
SITE 1 -> site_id = 1
SITE 2 -> site_id = 2
...
SITE N -> site_id = N
```

There is no canonical `SITE 0`.

Protocol v3.2 is canonical:

```text
magic:            PLASMA32
protocol_version: 3.2
identity:         site_id = 1..N
```

Protocol v3.1 remains an explicit compatibility adapter only:

```text
v3.1 channel_id 0 -> canonical SITE 1
v3.1 channel_id 1 -> canonical SITE 2
...
```

New code must not treat `site_id == channel_id` as an invariant, dual-send `channel_id` in v3.2 requests, or introduce new product/domain behavior using retired Programmer/Channel vocabulary.

Repository layout:

```text
pl/                 Zynq PL RTL, constraints, simulation, verification, Vivado build assets
software/python/    PPU control plane, Protocol v3.2 TCP server, CLI, REST gateway, optional Manager, tests
software/web/       Plasma PPU Console
scripts/            integration/deployment and service-control scripts
docs/               architecture, development, and deployment documentation
```

## 2. Source-of-truth priority

Do not assume chat history or older documentation is current. When sources disagree, use this priority order:

1. Executable code and checked-in configuration.
2. `scripts/plasmactl` for integration-host operational behavior.
3. `software/python/pyproject.toml` and `software/web/package.json` for toolchain/dependency requirements.
4. Current tests.
5. Current architecture/development documentation.
6. Historical/legacy documents and discussion.

If an inconsistency is found, report it explicitly. Do not silently propagate stale behavior. Update documentation together with intentional behavior changes.

## 3. Execution zones

### 3.1 Cloud / isolated software engineering

The isolated software-engineering environment may edit source, run tests that do not require site-specific services or hardware, and deliver changes on an `agent/*` branch through a pull request.

Repository entry points:

```bash
bash scripts/codex-cloud-setup.sh
bash scripts/codex-cloud-test.sh
```

Maintenance entry point:

```bash
bash scripts/codex-cloud-maintenance.sh
```

Cloud/isolated tests do not prove integration-host deployment, Vivado implementation, Z2 runtime behavior, FPGA I/O behavior, or real IC programming. Do not add integration-host SSH keys, Z2 credentials, GitHub tokens, board certificates, or deployment secrets merely to collapse these validation boundaries.

### 3.2 Integration / deployment host

The integration host owns deterministic cross-stack validation, shared runtime deployment, and Vivado integration. Machine names, usernames, private addresses, and absolute paths are operator-local configuration; public repository guidance uses `$PLASMA_REPO` and an integration-host alias.

Before modifying an integration-host workspace:

```bash
cd "$PLASMA_REPO"
git status -sb
git branch --show-current
git log -1 --oneline
git fetch origin main
```

Never overwrite unrelated user changes. If the worktree contains unrelated modifications, keep them untouched and limit edits to the requested scope.

### 3.3 Z2 target / hardware validation

Z2 owns embedded runtime, PS/PL integration, FPGA loading, target-interface behavior, electrical behavior, and hardware validation.

A passing Cloud, CI, or integration-host Mock test must never be reported as a passing Z2 or real-target test.

## 4. Current software architecture

Current implemented PPU-local path:

```text
Browser / Plasma PPU Console
        |
        | HTTP REST polling
        v
Plasma Web REST Gateway
        |
        | Plasma Protocol v3.2 / PLASMA32
        v
Plasma Server :9900
        |
        v
SiteManager / SiteWorker
        |
        v
Interface / Handler
        |
        v
MockInterface today; Z2/FPGA/real-target validation remains a separate stage
```

Optional implemented fleet path:

```text
Fleet client
    |
    v
Plasma Manager (read-only registry / aggregation)
    |
    +--> PPU A Plasma Web REST Gateway -> local execution
    +--> PPU B Plasma Web REST Gateway -> local execution
    +--> ...
```

Important implementation facts:

- The current Plasma Web REST Gateway uses Python standard-library `ThreadingHTTPServer`.
- It is **not FastAPI**.
- It does **not use WebSocket**.
- The Web Console currently uses REST polling.
- `plasma_manager` is an optional read-only fleet service using manually configured PPU Gateway endpoints; it is not required for local PPU execution.
- The current Manager does not provide command routing, central scheduling, discovery, auth policy, firmware rollout, Fleet Web UI, or `plasmactl`/systemd deployment integration.
- A successful Mock programming flow does not prove real-target hardware programming.

Do not introduce FastAPI/WebSocket merely because they were discussed as a future option. Such a migration requires an explicit task, corresponding architecture/API decisions, and tests.

## 5. Python environment and domain rules

Python project:

```text
software/python/
```

`pyproject.toml` is authoritative for Python requirements. The declared baseline is Python >= 3.11.

Preferred direct test command inside the configured Python environment:

```bash
cd software/python
.venv/bin/python -m pytest -q
```

`pytest` is the repository-wide Python test runner. Existing `unittest.TestCase` classes may remain while pytest collects them; do not reintroduce a separate unittest execution contract.

Canonical Python/domain code uses:

```text
PPUConfig
SiteConfig
SiteManager
SiteWorker
SiteState
ppu_id
facility_id
site_id
```

Legacy `Programmer*`, `Channel*`, `programmer/channels`, and `channel_id` may remain only in explicitly documented compatibility adapters/tests.

## 6. Web environment

Web project:

```text
software/web/
```

Use `package.json` as the source of truth for the current Web stack and versions. The project uses React + TypeScript and currently includes Next.js/Vinext and Vite tooling. Node.js must satisfy the engine declared in `package.json`.

Normal checks:

```bash
cd software/web
npm run lint
npm test
npm run validate:artifact
```

The Web Console is a PPU Console. It must discover PPU/Site topology from canonical status rather than hard-code an eight-Site product assumption. New job requests send one-based `site_id` only.

Do not assume production Z2 needs Node.js, npm, or the development server merely because the integration host uses them for development/build/demo work.

## 7. Runtime services and ports

Service management is defined by `scripts/plasmactl`.

| systemd service | Default port | Canonical role |
|---|---:|---|
| `plasma-server.service` | 9900 | Plasma PPU Programming Server / Protocol v3.2 TCP Server |
| `plasma-web.service` | 18080 | Plasma Web REST Gateway |
| `plasma-vite.service` | 5173 | Plasma PPU Console development/demo runtime |

Useful commands:

```bash
plasmactl status
plasmactl ports
plasmactl test
plasmactl restart
plasmactl logs
plasmactl deploy
```

`plasmactl test` is the preferred full integration-host validation for cross-stack changes.

Normal deployment flow:

```text
GitHub main
   -> fast-forward update
   -> re-exec latest plasmactl
   -> full relevant validation
   -> regenerate/reconcile systemd units
   -> restart services
   -> health check
```

Do not bypass failed tests and restart new code as if validation succeeded.

## 8. Site execution invariants

Unless a real shared resource requires synchronization:

- Sites execute independently.
- A Site must not wait for an unrelated Site pipeline.
- Per-Site cancellation must not cancel unrelated Sites.
- Batch cancellation is authoritative for batch classification when it races terminal job success, while the underlying final job result remains truthful.
- `program` means write only; a complete programming flow is composed explicitly as `erase -> program -> verify` when selected.
- Batch operation selection may include any subset of Erase / Program / Verify / Read.

## 9. Service and process safety

Before stopping a process, identify it first. Use `plasmactl ports`, `ss`, and `ps -fp PID` as appropriate.

Never use broad destructive process commands such as:

```text
pkill python
pkill node
killall python
killall node
```

Do not stop unrelated host services, networking, SSH, storage, containers, or other applications while working on Plasma unless the task explicitly requires it and the impact is understood.

Do not expose internal service ports directly to an untrusted network as a shortcut for connectivity problems.

## 10. Autonomous task execution contract

Treat requests such as:

```text
Implement <feature>.
Fix <bug>.
Continue PR #N until merge-ready.
Resolve the CI failure.
```

as authorization to perform routine engineering work necessary to reach the stated goal within this repository and the safety boundaries below.

Routine autonomous work includes:

- inspect repository, history, configuration, tests, logs, PRs, and CI;
- fetch/read Git state;
- fast-forward a clean local `main` when only behind `origin/main`;
- create/switch to `agent/<feature>` branches;
- edit files within scope;
- add/update tests and documentation required by the change;
- run focused and full relevant validation, builds, linters, and artifact checks;
- inspect diffs and generated output;
- create focused feature-branch commits;
- push feature branches;
- create/update PRs;
- inspect and repair deterministic CI failures caused by the branch;
- rerun a failed CI check once when evidence supports transient flakiness;
- mark a PR ready for review only when it is actually merge-ready.

Do not turn routine engineering procedure into user-operated command relaying when the agent can perform the work directly.

## 11. Protected approval gates — STOP and ask the user

Explicit user approval is required before:

1. **Merge/integration to `main`**
   - merge a PR to `main`;
   - directly commit code-changing feature work to `main`;
   - close/replace a PR in a way that discards reviewed work.

2. **Deployment/runtime changes**
   - `plasmactl deploy`;
   - restart shared Plasma services to activate new code;
   - change active systemd definitions, public routing, firewall/network exposure, or shared runtime configuration.

3. **Hardware-affecting operations**
   - program a real IC;
   - change DUT power/voltage;
   - load a new FPGA bitstream onto connected hardware;
   - change FPGA I/O behavior on a connected system;
   - perform any action with credible electrical/hardware risk.

4. **Destructive or history-rewriting Git operations**
   - `git reset --hard`;
   - `git clean -fd` or equivalent destructive cleanup;
   - force checkout/restore that discards user work;
   - rebase a published/shared branch;
   - `git push --force` / `--force-with-lease`;
   - delete remote branches/tags that may contain user work.

5. **Material architecture/security decisions**
   - incompatible protocol/API changes without an already-defined migration contract;
   - credential/access/security policy changes with nontrivial tradeoffs;
   - architecture choices with materially different cost, compatibility, safety, or maintainability consequences;
   - substantial scope expansion beyond the assigned goal.

When a protected gate is reached, stop at the safest clean checkpoint, summarize evidence/tradeoffs, and request the smallest necessary decision.

## 12. Merge-ready definition

A feature/PR is merge-ready only when all applicable conditions are true:

- intended implementation is complete;
- branch scope is clean and unrelated edits are absent;
- focused tests pass;
- full relevant validation passes;
- diff whitespace/syntax checks pass where applicable;
- committed diff was reviewed for correctness, security, generated files, and scope;
- feature branch is pushed;
- PR accurately describes behavior, validation, limitations, and hardware status;
- required CI checks pass;
- no blocking review findings remain;
- GitHub reports the PR mergeable, or straightforward non-destructive integration has been completed and retested;
- no validation claim exceeds what was actually observed.

At that point, stop and request approval to merge to `main`.

## 13. Git publication policy

Treat `main` as integration/deployment branch, not as an agent scratch branch.

Before code-changing work:

```bash
cd "$PLASMA_REPO"
git status -sb
git branch --show-current
git log -1 --oneline
git fetch origin main
```

If a clean local `main` is only behind `origin/main`, synchronize using fast-forward only. Do not silently merge/rebase divergent history.

New features, bug fixes, refactors, protocol changes, API changes, and hardware-interface changes normally use:

```text
agent/<short-feature-name>
```

Never stage or commit unrelated user work. Never force-push or rewrite published history merely for graph aesthetics.

After a reviewed feature is merged to GitHub `main`, deployment remains a separate approval gate.

## 14. Validation policy

Run the smallest relevant checks during development, then full relevant validation before declaring completion or merge-ready.

Python-only:

```bash
cd software/python
.venv/bin/python -m pytest -q
```

Web-only:

```bash
cd software/web
npm run lint
npm test
npm run validate:artifact
```

Cross-stack/deployment/config/API/release-affecting integration-host changes:

```bash
plasmactl test
```

Testing layers are distinct:

```text
Unit / Source
    -> SSR / rendered HTML
    -> Playwright browser E2E
    -> deterministic Visual Regression
    -> deployment/runtime validation
    -> Z2/hardware validation when applicable
```

A passing lower layer does not prove the next layer. Do not claim runtime verification if code has not been activated. Do not claim FPGA or hardware validation from Mock tests.

## 15. FPGA / PL rules

`pl/` contains FPGA/PL work for Z2. RTL, XDC, register maps, Vivado scripts, bitstreams, and hardware-visible interfaces are contracts.

New production RTL uses SystemVerilog and follows `pl/AGENTS.md`, `docs/development/fpga-development-guide.md`, and `docs/development/fpga-verification-guide.md`.

Canonical repeated programming-resource terminology is **Site**, including the production placeholder `pl/rtl/site/`. Do not create new production `channel` modules/directories merely from legacy software terminology; use `channel` only when it genuinely denotes a lower-level protocol/bus concept and document that distinction.

When PL-visible behavior changes:

- check Python/PYNQ register access;
- check register-map documentation;
- check clock/reset/CDC and XDC/timing constraints;
- run appropriate simulation/lint/SVA/cocotb validation;
- do not claim synthesis/implementation/timing/bitstream success unless actually run;
- do not claim Z2 hardware success from software tests.

## 16. Z2 production direction

Z2 is the intended embedded PPU controller/runtime, not a clone of the integration workstation.

Expected runtime responsibilities, subject to actual implementation/validation:

```text
Embedded Linux
Python Plasma runtime
PYNQ / FPGA runtime
Plasma Server / API layer
FPGA bitstream + HWH
configuration / target definitions
production Web assets or selected Web runtime
system services
logs / diagnostics
```

Development-only components such as Vivado, pytest, npm build tooling, source-control credentials, and developer SSH keys should not automatically be included in a production image.

Before standardizing a Z2 Python environment, verify compatibility with PYNQ/XRT first. Do not blindly clone the integration-host Python virtual environment onto Z2.

## 17. Current known boundaries / technical debt

Agents must not silently propagate these facts into wrong assumptions:

1. Python supports >=3.11; CI and integration host may use different allowed minor versions.
2. Integration deployment uses Plasma Web REST Gateway port 18080 while `plasma_web.gateway` retains a code-level local default of 8080.
3. The current Gateway is standard-library HTTP + REST polling, not FastAPI/WebSocket.
4. The current Web stack includes React/TypeScript plus Next.js/Vinext and Vite tooling; inspect `package.json` before making stack assumptions.
5. Protocol v3.1 compatibility remains temporarily supported; removing it is a separate deprecation decision.
6. Plasma Manager currently implements manual read-only PPU registry and fleet aggregation only; command routing, scheduling, discovery, authentication policy, Fleet UI, and deployment integration remain future work.
7. Mock/software validation still does not prove Z2/FPGA/OpenOCD/real-target behavior.

## 18. Communication and completion report

Report at meaningful engineering checkpoints rather than after every routine command. Interrupt the user immediately only for:

- a protected approval gate;
- a material ambiguity requiring a product/architecture decision;
- a safety/security issue;
- missing access that genuinely blocks progress;
- an unexpected state where continuing risks user work.

At completion/merge-ready/blocker, report at minimum:

```text
Changed:
- files/behavior changed

Validated:
- exact meaningful checks and results

Not validated:
- runtime/hardware/environment checks not actually performed

Repository state:
- branch / important HEAD
- PR / CI state
- whether merge, deploy, restart, history rewrite, or hardware action occurred

Next approval gate:
- exact approval required, if any
```

Never report a test, deployment, FPGA build, or hardware programming operation as successful unless it was actually executed and observed.

## 19. Workspace and information boundary

Treat the checked-out Plasma repository root (`$PLASMA_REPO`) as the normal workspace boundary for AI-assisted development.

- Read/create/modify/delete files only inside the repository unless the task genuinely requires an external resource and that access is already explicitly authorized.
- Keep ordinary development commands inside the repository or its subdirectories.
- Do not inspect unrelated repositories, personal files, credentials, SSH configuration, container data, or system configuration as ordinary Plasma work.
- Do not commit usernames, private hostnames, workstation inventory, keys, tokens, or other operator-specific infrastructure metadata into public guidance.
- If a task cannot be completed without leaving the workspace boundary, stop and explain exactly what external resource is needed and why.

This policy is not an OS sandbox. Editor/agent permissions should still enforce project-scoped access where possible.
