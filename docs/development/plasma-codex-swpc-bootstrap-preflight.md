# PLASMA SWPC Codex bootstrap prerequisite inspection (Issue #981)

**Status: Gate 1 A approved; source-only addition to the implementation plan. This workflow is not the dedicated Codex worker.**

## Why this exists

The original read-only Codex pilot was merged in PR #985, but requires a dedicated `SWPC-plasma-codex` runner and Linux account. A GitHub Issue or successful contract check does not prove the runner exists or is online. GitHub connector access does not expose the private Actions runner registration API.

To avoid interrupting ongoing ST, NXP, Microchip and Z2 work, this next step uses the already registered and restricted `SWPC-plasma-ci` runner for **inventory only**, not execution. It does not register a runner or contact Z2 / USB Hub / LA.

## Safe trigger

After this PR is merged through a separately approved **Gate 2**, an authenticated `physicslu` GitHub Issue comment on **Issue #981** can trigger:

```text
/plasma-codex preflight 981
```

The Actions `issue_comment` guard and a separately validated, trusted GitHub event payload must agree on the exact actor, Issue, repository, comment text, comment author, sender, event action and `main` ref.

Unlike the Codex pilot command `/plasma-codex pilot 981`, this command only inventories whether its prerequisites are present. Both commands are fixed and scoped. It is **not** arbitrary command execution.

The workflow checks out the event's trusted main-branch SHA and runs the inspection using `[self-hosted, linux, x64, plasma-integration]`. It requires host `SWPC`, Runner `SWPC-plasma-ci`, Linux account `plasma-ci` and non-root execution.

## What it checks

- `plasma-codex` user and `plasma-monitor` group existence.
- `/run/plasma-codex` directory ownership, group and mode `2770`.
- Availability of `tmux`, Git, GNU timeout and Codex in the existing CI account's PATH.
- Whether `codex --version` and `codex exec --help` return successfully. **No agent session** is launched, and command outputs are not saved.
- The expected GitHub/host execution identity.

Results are limited to booleans/status codes in `plasma-codex-swpc-preflight-981.json`, uploaded with SHA-256. No secrets, account configuration, actual environment variable values, arbitrary process lists, Z2 address, device contents or hardware evidence are exposed.

**Not verified by this check:** whether `SWPC-plasma-codex` has been registered or is connected, whether its separate Codex account is authenticated, whether the Codex sandbox is effective, whether OS device/network isolation is sufficient, or whether any Z2/USB Hub/LA integration works. These remain `NOT_CHECKED`.

## Acceptance and next engineering stage

A passing workflow means **the observation executed safely**, not that the dedicated worker is ready. The JSON report contains explicit prerequisites/unknowns and must be assessed before provisioning the independent runner.

The proper next stage remains:

1. Provision a separate `plasma-codex` Linux identity and new GitHub Runner with the uniquely scoped `plasma-codex` label; isolate it from privileged groups, all hardware credentials and the existing PPU services.
2. Establish operator-visible tmux socket ownership and persistent, redacted logs without leaking Codex authentication secrets.
3. Validate current Codex CLI flags and non-interactive authentication under the **new** worker identity.
4. Run PR #985's fixed **read-only** pilot after those prerequisites are satisfied; collect actual live tmux/CI/exit-code evidence.
5. Only after the above PASS propose the writable agent worker, job registry and hardware capabilities with separate exact per-task Gate 1 scope, always preserving Gate 2 merges.

This PR itself neither installs nor reconfigures host accounts/runners/services, accesses hardware, triggers the worker pilot, or merges to main. It requires normal Gate 2 approval before the Issue command is usable. No extra owner approval gate is invented for routine in-scope software development.
