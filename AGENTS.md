# Plasma Codex Autonomous Development Contract

This file is the primary operating contract for AI coding agents working on the Plasma repository.
Read it before making code, configuration, deployment, hardware, or documentation changes.

The default operating model is **goal-oriented autonomous execution with explicit approval gates**.
When the user assigns a feature, bug, maintenance task, CI repair, or PR objective, the agent should normally carry the task through the routine engineering lifecycle without asking the user to relay shell commands or approve every intermediate step.

Routine autonomous work includes repository inspection, feature-branch work, implementation, focused validation, full relevant validation, diff review, focused commits, feature-branch pushes, pull-request maintenance, and CI troubleshooting.

The agent must stop for explicit approval before crossing a protected boundary such as merging to `main`, deploying/restarting shared runtime services, performing hardware-affecting operations, rewriting published Git history, or making a material architecture/security tradeoff that cannot be resolved from the repository and task requirements.

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
Deployment branch: main
```

Do not treat SWPC as the final production image for Z2. SWPC may contain development-only tools that should not be copied to the embedded target.

Before modifying files on SWPC:

```bash
cd /storage/projects/plasma
git status -sb
git branch --show-current
git log -1 --oneline
git fetch origin main
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

Do not replace pytest with unittest based on stale documentation or CI configuration.
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

## 9. Autonomous task execution contract

### 9.1 Goal-oriented execution

Treat a user request such as:

```text
Implement <feature>.
Fix <bug>.
Continue PR #N until merge-ready.
Resolve the CI failure.
```

as authorization to perform the routine engineering work necessary to reach that stated goal within the repository and safety boundaries in this file.

Do **not** require the user to copy shell commands between ChatGPT, Codex, and SWPC for ordinary development steps.
Do **not** stop merely to ask permission for routine inspection, editing, tests, diff review, focused commits, feature-branch pushes, PR updates, or CI investigation when those actions are clearly within the assigned goal.

Prefer independent engineering judgment grounded in source code, tests, current configuration, and observable results.
Ask the user only when a protected approval gate or genuine material ambiguity is reached.

### 9.2 Actions the agent may perform autonomously

Within an assigned development/maintenance goal, the agent may normally:

- Inspect repository state, history, configuration, tests, logs, and current PR/CI state.
- Run `git fetch` and other read-only Git inspection commands.
- Fast-forward a clean local `main` to `origin/main` before starting new feature work.
- Create and switch to an appropriate `agent/<feature>` branch.
- Modify files within the task scope.
- Add or update tests and documentation needed by the change.
- Run focused tests, full relevant validation, builds, linters, and artifact checks.
- Inspect and review `git diff`, `git diff --check`, staged diffs, and generated output.
- Stage only intended files and create focused commits on a feature branch.
- Push a feature branch and set/update its upstream.
- Create or update a pull request for the feature branch.
- Update PR descriptions/comments and mark a draft PR ready for review when the branch is actually merge-ready.
- Inspect GitHub Actions results and logs.
- Investigate and correct CI failures caused by the branch or by deterministic test/infrastructure issues that are reasonably in scope.
- Rerun a failed CI check once when there is concrete evidence the failure is transient/flaky; repeated reruns must not substitute for root-cause analysis.
- Add follow-up commits to the same feature branch when review or CI identifies a narrow correction.

Routine autonomous publication is limited to **feature branches and their PRs**. It does not authorize merging to `main` or deploying runtime changes.

### 9.3 Protected approval gates — stop and ask the user

Explicit user approval is required before any of the following:

1. **Merge/integration to `main`**
   - merging a PR to `main`
   - directly committing code-changing feature work to `main`
   - closing/replacing a PR in a way that discards reviewed work

2. **Deployment/runtime changes**
   - `plasmactl deploy`
   - restarting shared Plasma services to activate new code
   - changing systemd service definitions, public routing, firewall/network exposure, or production/demo runtime configuration when the effect is operational rather than test-only

3. **Hardware-affecting operations**
   - programming a real IC
   - changing DUT power/voltage
   - loading a new FPGA bitstream onto hardware
   - changing hardware I/O behavior on a connected system
   - any action with credible risk of damaging or electrically stressing hardware

4. **Destructive or history-rewriting Git operations**
   - `git reset --hard`
   - `git clean -fd` or equivalent destructive cleanup
   - force checkout/restore that discards user work
   - rebase of a published/shared branch
   - `git push --force` / `--force-with-lease`
   - deleting remote branches/tags that may contain user work

5. **Material design/security decisions**
   - incompatible protocol/API changes without a clear repository-defined migration path
   - security/credential/access-policy changes with nontrivial tradeoffs
   - architecture choices with materially different cost, compatibility, safety, or maintainability consequences when the task does not already select one
   - scope expansion that substantially changes the original goal

When a protected gate is reached, stop at the safest clean checkpoint, summarize the state and tradeoff, and ask for the smallest necessary decision.

### 9.4 Do not interrupt for routine decisions

The following are normally **not** reasons to stop and ask the user:

- which focused test command to run
- whether to inspect a file, log, diff, or CI job
- whether to add a test required to prove the requested behavior
- whether to create a normal feature-branch commit after successful review/validation
- whether to push that feature branch so CI can run
- whether to fix a clear CI failure on that feature branch
- whether to update the PR body with validation results
- whether to make a small deterministic cleanup discovered during the assigned task when it is necessary for correctness and remains tightly scoped

Do the work and report meaningful results instead of turning routine engineering procedure into user-operated command relaying.

### 9.5 Definition of merge-ready

When asked to bring a feature or PR to merge-ready state, continue autonomously until all applicable conditions are true:

- intended implementation is complete
- branch scope is clean and unrelated edits are absent
- focused tests pass
- full relevant repository validation passes
- `git diff --check` passes
- staged/committed diff has been reviewed for correctness, security, generated files, and scope
- feature branch is pushed
- PR accurately describes behavior, validation, limitations, and hardware status
- required CI checks pass
- no blocking review findings remain
- GitHub reports the PR mergeable, or any non-destructive conflict resolution clearly within scope has been completed and retested
- no claim exceeds what was actually validated

At that point, stop and request approval to merge to `main`.

## 10. Git workflow and publication policy

The Git workflow exists to keep `main` reviewable and deployable and to prevent an agent from mixing unrelated user work into a change.

### 10.1 Inspect before changing anything

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

### 10.2 Use feature branches for code changes

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

### 10.3 Validate and review before commit

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

### 10.4 Autonomous feature-branch commits

When the assigned goal authorizes autonomous execution under Section 9, the agent may commit reviewed, validated work on the task's feature branch without a separate user approval for each commit.

Before each commit:

1. Stage only files that belong to the requested change.
2. Prefer explicit file paths instead of `git add -A` when unrelated modifications may exist.
3. Inspect exactly what will be committed:

```bash
git diff --cached --check
git diff --cached
```

4. Create a focused commit with a concise message describing the complete change.

Never stage or commit unrelated user work.

If the user explicitly requested a review-only or no-commit task, that narrower instruction overrides autonomous commit permission.

### 10.5 Feature-branch publication

Under an autonomous task, the agent may push the feature branch and create/update its PR without separate approval, because this is necessary for CI and review and does not change deployed `main`.

The normal autonomous feature flow is:

```text
inspect/synchronize clean main
    -> create/use feature branch
    -> implement
    -> focused tests
    -> full validation
    -> diff review
    -> stage intended files
    -> review staged diff
    -> commit
    -> push feature branch
    -> create/update PR
    -> inspect CI/review
    -> fix branch/CI issues as needed
    -> merge-ready checkpoint
    -> STOP FOR USER MERGE APPROVAL
```

Do not force-push, rewrite a published branch, merge to `main`, tag a release, or deploy without explicit approval.
Never commit credentials, SSH private keys, tokens, `.env` secrets, or generated credentials.

### 10.6 Keeping a feature branch current

Do not rewrite published history merely to obtain a linear graph.
If a published feature branch falls behind `origin/main` but GitHub still reports it mergeable and CI is valid, rebasing is not required just for aesthetics.

If integration with newer `main` is actually necessary:

- fetch first and inspect divergence
- preserve a clean worktree
- prefer a non-destructive integration method on a published branch
- resolve straightforward, task-local conflicts only when the correct resolution is unambiguous
- rerun relevant validation after integration
- stop for user approval if resolution requires a design choice or would rewrite published history

### 10.7 `main` and deployment rules

Treat `main` as the integration/deployment branch, not as an agent scratch branch.
SWPC deployment behavior must remain fast-forward based; do not silently resolve deployment-branch divergence with an automatic merge or rebase.

`plasmactl update` and `plasmactl deploy` are intended to operate on the configured deployment branch (`main` by default).
Do not deploy an unreviewed feature branch as though it were the production/demo `main` branch.

After a feature is reviewed and merged to GitHub `main`, deployment still requires explicit user approval.
When approval is granted, the normal SWPC deployment sequence is:

```bash
plasmactl deploy
```

which performs the repository's update, full validation, service restart, and health checks according to `scripts/plasmactl`.

## 11. Validation policy

Run the smallest relevant checks during development, then run the full relevant validation before declaring the work complete or merge-ready.

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

When service behavior changed, service restart/runtime verification may be required eventually, but restarting the shared services is a protected approval gate.
Do not claim runtime verification if the new code has not actually been activated.
Do not claim hardware validation if only MockInterface tests ran.

### 11.1 CI failures

A failed required check blocks merge-ready status until it is understood and resolved.

When CI fails:

1. Inspect the exact workflow/job logs.
2. Determine whether the failure is caused by the feature, stale CI configuration, a deterministic infrastructure/test issue, or credible transient flakiness.
3. Reproduce locally where practical.
4. Fix the smallest correct layer; do not weaken correctness assertions merely to obtain a green check.
5. Push the focused fix and allow CI to rerun.
6. If evidence strongly supports a transient runner failure, one rerun is acceptable; repeated reruns without root-cause work are not.

### 11.2 Remote-session resilience

Long validation/build steps must not depend unnecessarily on an iPad/iPhone-to-Mac Remote session remaining connected.
The engineering operation should live as close as practical to the machine that owns the repository and build environment.

For long **non-destructive** tests/builds on SWPC, the agent may use a durable host-side execution pattern when useful, for example a background process with a known PID and log file, so a Remote UI disconnect does not destroy the work.

When doing so:

- record the exact command, PID, and log path
- ensure the command is non-interactive and non-destructive
- check its exit status/result before treating it as validated
- clean up temporary logs/processes when appropriate
- never background a deployment, service restart, destructive Git operation, or hardware operation merely to bypass an approval gate

Prefer short meaningful checkpoints over one unnecessarily long remote-controlled command chain.

## 12. Hardware / PL rules

`pl/` contains FPGA/PL work for the Z2 platform.
Treat RTL, XDC constraints, register maps, Vivado scripts, `.bit`, and `.hwh` artifacts as hardware-interface contracts.

When changing PL-visible behavior:

- Check whether Python/PYNQ register access must change.
- Check whether register-map documentation must change.
- Check whether simulation or hardware validation is required.
- Do not claim Vivado synthesis/implementation/bitstream success unless those steps were actually run.
- Do not claim Z2 hardware success from software Mock tests.
- Avoid hand-editing generated Vivado output unless the file is intentionally maintained as source.

Real IC programming, DUT power control, FPGA I/O changes, and target-voltage changes can affect hardware. They are protected approval-gate operations unless the user has explicitly authorized the specific hardware task and its scope.

## 13. Z2 production direction

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

## 14. Known current inconsistencies / technical debt

Agents should be aware of these items and must not silently propagate them:

1. `software/python/pyproject.toml` and `scripts/plasmactl` use pytest, while the current GitHub Python workflow still runs `unittest discover`; CI should eventually be aligned with the repository-defined test entry point.
2. SWPC development currently uses Python 3.11 while the GitHub Python workflow uses Python 3.12; this is valid under the declared `>=3.11` requirement but differences must be considered when diagnosing CI-only failures.
3. The SWPC operational Gateway port is 18080, while the Python gateway module has a code-level default of 8080.
4. Older architecture discussion may describe FastAPI/WebSocket, but the current checked-in Gateway uses Python standard-library HTTP and REST polling.
5. Older descriptions may call the Web stack simply React/TypeScript/Vite; current `package.json` also includes Next.js/Vinext. Always inspect the current package metadata before making stack assumptions.

When working near one of these areas, either resolve the inconsistency as part of the task or call it out clearly in the final report.

## 15. Agent communication and completion report

Prefer reporting at meaningful engineering checkpoints rather than after every routine shell command.
Do not require the user to relay command output between systems when the agent can inspect the relevant source, repository, CI, or log directly.

Interrupt the user immediately only for:

- a protected approval gate
- a material ambiguity requiring a product/architecture decision
- a safety/security issue
- missing credentials/access that genuinely blocks progress
- an unexpected state where continuing risks losing user work

When a task reaches completion, merge-ready state, or a blocker, report at minimum:

```text
Changed:
- files changed
- behavior changed

Validated:
- exact meaningful checks run
- pass/fail result

Not validated:
- hardware, service, deployment, or environment checks not actually performed

Repository state:
- branch
- HEAD/important commit(s)
- whether worktree is clean
- feature-branch push / PR / CI state
- whether any merge, deploy, restart, history rewrite, or hardware action was performed

Next approval gate:
- state exactly what user approval is required, if any
```

Be precise. Never report a test, build, service restart, deployment, FPGA build, or hardware programming operation as successful unless it was actually executed and observed to succeed.
