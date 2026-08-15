# Plasma Agent Development Guide

This file is the primary operating guide for AI coding agents working on the Plasma repository.
Use it before making code, configuration, deployment, or documentation changes.

## 1. Project purpose

Plasma is a multi-channel IC programming system using PYNQ-Z2 (Z2) as the hardware development platform.
The prototype currently enables CH0 and CH1 while keeping the software and RTL architecture extensible to 1–8 channels.

Repository layout:

```text
pl/                 Zynq PL RTL, constraints, simulation, Vivado build assets
software/python/    Plasma control plane, TCP server, CLI, REST gateway, tests
software/web/       Plasma Programmer Console
scripts/            SWPC deployment and service-control scripts
docs/               Architecture, development, deployment, hardware, and test documentation
```

## 2. Source-of-truth priority

Do not assume chat history or older documentation is current.
When sources disagree, use this priority order:

1. Executable code and checked-in configuration.
2. `scripts/plasmactl` for SWPC operational behavior.
3. `software/python/pyproject.toml` and `software/web/package.json` for toolchain/dependency requirements.
4. Current tests.
5. Documentation.
6. Historical discussion or assumptions.

If an inconsistency is found, report it explicitly and avoid silently choosing the older behavior.
Update the relevant documentation when behavior is intentionally changed.

## 3. Development host: SWPC

SWPC is the primary Plasma development, integration-test, build, and demo server.

```text
SSH:        gordon@swpc
Repository: /storage/projects/plasma
Branch:     main
```

Do not treat SWPC as the final production image for Z2. SWPC may contain development-only tools that should not be copied to the embedded target.

Before modifying files on SWPC:

```bash
cd /storage/projects/plasma
git status -sb
git log -1 --oneline
```

Never overwrite unrelated user changes.
If the worktree contains unrelated modifications, keep them untouched and limit edits to the requested scope.

## 4. Current software architecture

Current implemented path:

```text
Browser Web Console
        |
        | HTTP REST / polling
        v
Python REST Gateway
        |
        | Plasma protocol v3.1 over TCP
        v
Plasma Server :9900
        |
        v
Channel interface / handler
        |
        v
MockInterface today; Z2/FPGA hardware integration is still a separate validation stage
```

Important: the current Python Web Gateway is implemented with Python standard-library `ThreadingHTTPServer`.
It is NOT currently FastAPI and does NOT currently use WebSocket.
Do not introduce FastAPI/WebSocket merely because they were discussed as a future architecture; make that migration only when the task explicitly requires it and update architecture documentation and tests together.

Prototype Web status is polled from the Gateway. A successful Mock programming flow does not prove real target hardware programming.

## 5. Python environment

Python project:

```text
software/python/
```

`pyproject.toml` is authoritative for Python requirements.
Current project requirement is Python >= 3.11.
The normal SWPC virtual environment is:

```text
/storage/projects/plasma/software/python/.venv
```

Preferred direct test command:

```bash
cd /storage/projects/plasma/software/python
.venv/bin/python -m pytest -q
```

Do not replace pytest with unittest based on stale documentation.
If a Python dependency changes, update `pyproject.toml` and verify the SWPC install/deploy path still works.

## 6. Web environment

Web project:

```text
software/web/
```

Use `package.json` as the source of truth for the current web stack and versions.
The project uses React + TypeScript and currently includes Next.js/Vinext and Vite-based tooling.
Node.js must satisfy the engine declared in `package.json` (currently >= 22.13.0).

Normal checks:

```bash
cd /storage/projects/plasma/software/web
npm run lint
npm test
npm run validate:artifact
```

Do not assume the production Z2 needs Node.js, npm, or the development server merely because SWPC uses them for development/build/demo work.
The eventual embedded deployment should minimize runtime dependencies and deploy only what the selected production Web architecture actually requires.

## 7. SWPC services and ports

SWPC service management is defined by `scripts/plasmactl`.
The current user systemd services are:

| Service | Port | Role |
|---|---:|---|
| `plasma-server.service` | 9900 | Plasma v3.1 TCP Server |
| `plasma-web.service` | 18080 | Python HTTP REST Gateway |
| `plasma-vite.service` | 5173 | Web Console development/demo service |

Operational SWPC Gateway port is **18080**.
Although `plasma_web.gateway` has its own code-level default, do not change SWPC deployment back to port 8080 unless the deployment design is intentionally changed.

Useful commands:

```bash
plasmactl status
plasmactl ports
plasmactl test
plasmactl restart
plasmactl logs
plasmactl deploy
```

`plasmactl test` is the preferred full SWPC validation because it runs the repository's Python and Web checks together.

The normal deployment flow is:

```text
GitHub main
   -> SWPC fast-forward update
   -> full test
   -> restart services
   -> health check
```

Do not bypass failed tests and restart the new code as if validation succeeded.

## 8. Service and process safety

Before stopping a process, identify it first.
Use `plasmactl ports`, `ss`, and `ps -fp PID` as appropriate.

Never use broad destructive process commands such as:

```text
pkill python
pkill node
killall python
killall node
```

Do not stop Apache, Nextcloud, Docker services, networking, Tailscale, SSH, or unrelated SWPC services while working on Plasma unless the task explicitly requires it and the impact is understood.

Do not expose internal service ports directly to the public Internet as a shortcut for fixing connectivity.

## 9. Git workflow and publication policy

The Git workflow exists to keep `main` reviewable and deployable and to prevent an agent from mixing unrelated user work into a change.

### 9.1 Inspect before changing anything

Before code-changing work, inspect the repository first:

```bash
cd /storage/projects/plasma
git status -sb
git branch --show-current
git log -1 --oneline
git fetch origin main
```

After fetching, determine whether the local branch is ahead of or behind `origin/main` before proceeding.
Fetching is safe because it updates remote-tracking refs without modifying the working tree.

If local `main` is clean and only behind `origin/main`, synchronize it using fast-forward only:

```bash
git pull --ff-only origin main
```

Do not silently merge or rebase divergent history.
If the worktree already contains modifications, do not pull, merge, rebase, reset, stash, or discard them until their ownership and purpose are understood.

### 9.2 Use feature branches for code changes

New features, bug fixes, refactors, protocol changes, API changes, and hardware-interface changes must not normally be developed directly on `main`.
After synchronizing a clean `main`, create a dedicated branch before editing code.
AI-created development branches should normally use:

```text
agent/<short-feature-name>
```

Example:

```bash
git switch -c agent/read-ic-v1
```

If requested feature work has already been started as uncommitted changes on `main`, do not discard or recreate the work.
Create a feature branch from the current state while preserving the existing working-tree changes:

```bash
git switch -c agent/<short-feature-name>
```

Then verify that all intended modifications are still present with `git status -sb` and `git diff --stat`.

Small documentation-only or explicitly requested repository-maintenance changes may be applied directly to `main` when the user intentionally requests that workflow, but code-changing feature development should use a feature branch.

### 9.3 Validate and review before commit

During development, run focused checks as needed.
Before declaring the implementation ready for review, run the full validation required by the affected scope and then inspect the diff:

```bash
git diff --check
git diff --stat
git diff
```

For cross-stack Plasma changes, normally run:

```bash
plasmactl test
```

Do not equate passing tests with architectural correctness. The diff must still be reviewed for scope, interface changes, security impact, generated files, and unintended edits.

### 9.4 Do not commit before review approval

Unless the user explicitly requested commit as part of the task, stop after implementation, validation, and diff review.
Do not automatically commit merely because tests pass.

When commit approval is given:

1. Stage only files that belong to the requested change.
2. Prefer explicit file paths instead of `git add -A` when unrelated modifications may exist.
3. Inspect exactly what will be committed:

```bash
git diff --cached --check
git diff --cached
```

4. Create a focused commit with a concise message describing the complete change.

Never stage or commit unrelated user work.

### 9.5 Publication requires explicit approval

Do not commit, push, merge, rebase, tag, force-update a branch, or open a PR unless the user explicitly authorizes the corresponding publication action.

The normal feature publication flow is:

```text
synchronize main
    -> create feature branch
    -> implement
    -> focused tests
    -> full validation
    -> diff review
    -> user approval
    -> stage intended files
    -> review staged diff
    -> commit
    -> push feature branch
    -> pull request
    -> review
    -> merge to main
    -> deploy main
```

Never use destructive Git operations such as `git reset --hard`, forced checkout, or forced push unless explicitly requested, justified, and the consequences are understood.
Never commit credentials, SSH private keys, tokens, `.env` secrets, or generated credentials.

### 9.6 `main` and deployment rules

Treat `main` as the integration/deployment branch, not as an agent scratch branch.
SWPC deployment behavior must remain fast-forward based; do not silently resolve divergence with an automatic merge or rebase.

`plasmactl update` and `plasmactl deploy` are intended to operate on the configured deployment branch (`main` by default).
Do not deploy an unreviewed feature branch as though it were the production/demo `main` branch.

After a feature is reviewed and merged to GitHub `main`, the normal SWPC deployment sequence is:

```bash
plasmactl deploy
```

which performs the repository's update, full validation, service restart, and health checks according to `scripts/plasmactl`.

## 10. Validation policy

Run the smallest relevant checks during development, then run the full relevant validation before declaring the work complete.

For Python-only changes:

```bash
cd software/python
.venv/bin/python -m pytest -q
```

For Web-only changes:

```bash
cd software/web
npm run lint
npm test
npm run validate:artifact
```

For cross-stack, deployment, configuration, API, or release-affecting changes on SWPC:

```bash
plasmactl test
```

When service behavior changed, additionally verify:

```bash
plasmactl restart
plasmactl status
```

Only restart services when the task scope allows runtime changes.
Do not claim hardware validation if only MockInterface tests ran.

## 11. Hardware / PL rules

`pl/` contains FPGA/PL work for the Z2 platform.
Treat RTL, XDC constraints, register maps, Vivado scripts, `.bit`, and `.hwh` artifacts as hardware-interface contracts.

When changing PL-visible behavior:

- Check whether Python/PYNQ register access must change.
- Check whether register-map documentation must change.
- Check whether simulation or hardware validation is required.
- Do not claim Vivado synthesis/implementation/bitstream success unless those steps were actually run.
- Do not claim Z2 hardware success from software Mock tests.
- Avoid hand-editing generated Vivado output unless the file is intentionally maintained as source.

Real IC programming, DUT power control, FPGA I/O changes, and target-voltage changes can affect hardware. Do not perform potentially destructive hardware operations unless explicitly within scope.

## 12. Z2 production direction

Z2 is the intended embedded programmer controller/runtime, not a clone of the SWPC development workstation.
Keep the future production image minimal.

Expected runtime responsibilities include, subject to actual implementation and validation:

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

Development-only components such as Vivado, pytest, npm build tooling, full source-control credentials, and developer SSH keys should not automatically be included in a production Z2 image.

Before standardizing a Z2 Python environment, verify compatibility with the PYNQ/XRT environment first. Do not blindly clone the SWPC Python virtual environment onto Z2.

## 13. Known current inconsistencies / technical debt

Agents should be aware of these items and must not silently propagate them:

1. `software/python/pyproject.toml` and `scripts/plasmactl` use pytest, while some documentation still mentions unittest.
2. The SWPC operational Gateway port is 18080, while the Python gateway module has a code-level default of 8080.
3. Older architecture discussion may describe FastAPI/WebSocket, but the current checked-in Gateway uses Python standard-library HTTP and REST polling.
4. Older descriptions may call the Web stack simply React/TypeScript/Vite; current `package.json` also includes Next.js/Vinext. Always inspect the current package metadata before making stack assumptions.

When working near one of these areas, either resolve the inconsistency as part of the task or call it out clearly in the final report.

## 14. Agent completion report

After making changes, report at minimum:

```text
Changed:
- files changed
- behavior changed

Validated:
- exact commands run
- pass/fail result

Not validated:
- hardware, service, deployment, or environment checks not actually performed

Repository state:
- branch
- whether worktree has remaining modifications
- whether any commit/push/merge was performed
```

Be precise. Never report a test, build, service restart, deployment, FPGA build, or hardware programming operation as successful unless it was actually executed and observed to succeed.
