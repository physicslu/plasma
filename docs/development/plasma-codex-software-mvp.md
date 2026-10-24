# PLASMA — Historical shared SWPC Codex worker for SW and LA2016

## Scope and operational model

**Gate 1 only: source changes and GitHub-hosted offline tests.** No software Codex
execution, device opening, Z2 SSH, LA PWM, USB Hub power action, host provisioning,
deployment or merge is approved by this change. A later separate Gate 2 is
required for merge. **Merge alone is not live-execution authorization.**

Use the existing, separately registered `SWPC-plasma-codex` GitHub runner and
non-root `plasma-codex` Linux user, with its existing `plasma-codex-io`
and `plasma-monitor` groups. Do not create another account, worker or
hardware-control service. The two retained historical fixed **workloads** are:

| Workload | Workflow | One exact owner command on Issue #981 |
| --- | --- | --- |
| C11 SW example | `.github/workflows/plasma-codex-software-mvp.yml` | `/plasma-codex hello-c 981` |
| LA2016 Direct PWM / capture | `.github/workflows/plasma-codex-la2016-direct.yml` | `/plasma-codex la2016-direct 981` |

Both retained workflows schedule the same `[self-hosted, linux, x64, plasma-codex]`
runner. They are **not** interchangeable authorization scopes. The former dedicated Z2 SWD-05 dispatch has been retired; the existing LA
workflow retains its OFF controls. Shared Path 2/3 Z2 execution and SSH
credentials are governed by their current Development Mode contracts, not
by this historical MVP workflow. Live readiness is not certified by hosted CI.

## Reason for the change (evidence, not speculation)

Original automatic SW pilot [Run #39190291831](https://github.com/physicslu/plasma/actions/runs/39190291831)
failed its broad software-only check before starting Codex. A separately
authorized **metadata-only** SWPC observation [Run #39196263411](https://github.com/physicslu/plasma/actions/runs/39196263411)
confirmed `NO_GO_REPRODUCED`: six existing USB character device paths
under `/dev/bus/usb` were **readable but not writable** as the worker;
their modes were `0664`, owner/group `root:root`. The first path was
`/dev/bus/usb/001/001`. The diagnostic did NOT read device contents
or command any hardware.

The old `test -r ... || test -w ...` check made a deliberately
hardware-capable HIL account fail for normal USB read access. Remove **only**
that broad DAC rejection from the fixed SW task. Instead, require the
known worker name, non-root user, loaded `plasma-codex-io` and
`plasma-monitor` groups, clean source checkout, forbidden privileged
group rejection, and absent exposed `SSH_AUTH_SOCK`. Do not change
host USB/udev permissions, Z2 credentials, or privileged groups.

**Security tradeoff:** The existing Linux worker account is hardware-capable.
A fixed *software intent* in a Codex prompt, workspace-write sandbox or
disabled workspace network is **not** an OS guarantee that USB/Z2/LA cannot
be accessed by the process. This design deliberately accepts one
owner-operated HIL worker rather than adding a separate isolated software
identity. Do not call the SW task physically isolated, or infer USB/LA
control safety from a CI success. A task accidentally operating a device
would be a safety incident, not an authorized HIL test.

## Manual work authorization, not automatic software execution

The prior one-shot postmerge authorization was deliberately bound to
PR #1033 / #1034; [Run #39190291831](https://github.com/physicslu/plasma/actions/runs/39190291831)
already consumed that activation and failed. Merely merging this PR must
**not** replay it. `scripts/plasma_codex_postmerge_dispatch.py` is left in
the repo as historical provenance logic, but **no active Workflow calls it**.

The fixed SW task uses the **same explicit Issue comment admission pattern**
as the existing Z2 and LA workflows:

1. After an independent Gate 2 merge, the sole trusted owner
   `physicslu` may make a **separate** deliberate `created` comment,
   exactly `/plasma-codex hello-c 981`, on Issue #981.
2. A GitHub-hosted `authorize` job verifies repository, actor,
   issue number, non-PR issue, exact comment, main ref, unmodified
   checked-out SHA and first-run attempt. Other comments never reach
   SWPC. PR and `push` events execute **hosted-only** contract checks.
3. After successful admission the dedicated runner rechecks identity,
   pinned SHA, clean worktree and bounded Codex CLI settings; model
   instructions explicitly prohibit hardware, SSH, USB and power
   operations. The task only produces
   `examples/hello-world/main.c` and may not overwrite an existing file.
4. GCC static/runtime acceptance and strict single-file patch admission
   are unchanged. GitHub-hosted Publisher validates the artifact
   separately and may **open** a PR; it cannot merge it.
5. The SW Issue command does **not** authorize Z2/LA/USB Hub/DUT
   physical actuation. Those workflows retain their own exact owner
   commands, bounded steps, watchdog/OFF/physical-recovery rules.

The C11 command is a *fixed example task*, **not** an arbitrary software
development dispatcher. It is not a promise that other SW jobs have been
implemented. If `examples/hello-world/main.c` is already present, the
worker intentionally rejects this fixed task rather than overwriting.

## Gate 1 validation and negative cases

GitHub-hosted contract tests check the changed SW Workflow plus the
**existing** Z2/LA Workflow contracts: same worker label/user, exact
owner commands, gated worker jobs, no new `workflow_dispatch`,
untrusted PR checkout, OS privilege escalation, or automatic hardware
operation from a `push`. The retired broad USB read/write predicate is
explicitly forbidden from returning in the SW preflight.

No live Codex, GCC on SWPC, physical waveform, power toggle,
FPGA reconfiguration or DUT access is performed during Gate 1 or
automatically on Gate 2. Live SW dispatch needs a **separate, explicit
owner Issue comment** after merge. Always verify the actual GitHub run
and evidence rather than assuming a successful contract equals live HIL.
