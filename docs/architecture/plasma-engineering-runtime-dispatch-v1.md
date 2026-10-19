# PLASMA Engineering Runtime Dispatcher v1 — Gate 1 implementation candidate

**Status: DEPLOYMENT NO-GO / Runtime disabled.** This PR introduces one generic
workflow plus deterministic authorization/worker adapters and adversarial tests.
It **does not** approve live SWPC, Codex, QEMU, Z2, FPGA, LA, USB Hub or DUT
operations. No merge occurs without the separate Gate 2.

## Development Mode owner-only dispatch (PR #1046 alignment)

This is a separate **development entry** within the **same reusable Workflow**,
not a new task-specific Workflow, Runner or Production Mode activation.
The earlier `workflow_dispatch` qualification path remains dormant.
The approved owner can issue an exact GitHub Issue **#981** comment:

```text
/plasma-dispatch run nine-nine-path2 981
```

The issue-comment event must come from `physicslu`; the hosted authorization
job loads `specs/engineering-dispatch/development-tasks-v1.json` from
**the event-pinned main commit**, resolves the fixed task, and passes its SHA
to the existing `SWPC-plasma-codex` Runner. The worker revalidates the
event/owner/ref/Runner identity and checks out the same SHA. It executes the
checked-in Python program without shell interpolation, verifies **81 products**
and the exact expected stdout SHA256, and uploads a short JSON receipt.

The task registry is reusable: changing the task changes a reviewed registry
entry rather than the GitHub Workflow. This first Development Mode route
supports fixed Path 2 CLI Python tasks; Path 3 Codex remains on its existing
owner-authorized pilot path until the generic agent-task admission is implemented.
Repeated idempotent development tests are allowed (no permanent Claim ref).
No SWPC run is triggered by PR/push; they execute **hosted offline tests only**.
The `PLASMA_ENGINEERING_DISPATCH_ENABLED` qualification guard and
`runtime-activation-v1.json` stay OFF, and no production capability is granted.
A shared, hardware-capable development Runner is not an implicit authorization
to operate USB, LA, Z2, FPGA, MMIO, hub power or a DUT.

**Gate 1 authorizes the test; GitHub issue comment is the executable event,
not a third approval gate.** Actual Path 2 PASS requires a GitHub
`development-execute` job with `RUNNER_NAME=SWPC-plasma-codex`,
exit code zero and a matching receipt. Hosted CI success is not real SWPC PASS.

## Authority and path mapping

Use the existing [Three-Path Model](../development/plasma-three-path-execution-model.md)
(PR #1041) and
[Dispatcher Gate 1A](plasma-engineering-dispatch-v1.md) as normative.
There are exactly two owner gates: Gate 1 approves scoped execution and Gate 2
approves *PR merge*. Creating a GitHub run is a technical action after Gate 1,
not a new owner gate.

| Path | Task type | Trusted executor | Output |
| --- | --- | --- | --- |
| 1 | Host-only | ChatGPT / GitHub-hosted CI | PR, CI, Gate 2 |
| 2 | Fixed CLI | Trusted main → Actions → isolated SWPC CLI worker | bounded exit code + SHA256 receipt; PR only if sources changed |
| 3 | Agentic | Trusted main → Actions → isolated SWPC Codex worker | bounded task evidence, then trusted broker PR/CI and Gate 2 |

**Only one** new reusable workflow:
`.github/workflows/plasma-engineering-runtime-dispatch.yml`.
Individual assignments are reviewed
`specs/engineering-dispatch/runtime-requests/<work_order_id>.json`
bundles, **not new workflows**. The current `runtime-requests` directory contains
no executable orders, deliberately.

The new Python adapter reuses the existing v1 Work Order schema, canonical
JSON hashing, permission and scope rules; `capabilities-v1.json` retains
`CONTRACT_ONLY_NO_RUNTIME_DISPATCH` and **every** `runtime_enabled=false`.
Initially only software cases are accepted:

- `path2-cli` ↔ `software-readonly`, fixed checked-in Python script in the
  Work Order allowed path list, argv array (never an interpolated shell).
- `path3-codex` ↔ `software-pr`, bounded prompt over predeclared repository paths.
- All hardware capabilities (`la2016-loopback`, `z2-readonly`,
  `z2-privileged`) remain denied. Approval of this PR does not permit
  hardware access, even read-only inventory.

## Admission, claims and replay

1. PR and push trigger **hosted `offline-contract` only**; never schedule SWPC.
2. A live owner-created `workflow_dispatch` could only admit after
   `PLASMA_ENGINEERING_DISPATCH_ENABLED == 'true'`, currently **not enabled**.
   Untrusted PR/push, non-owner dispatches or non-main refs fail closed.
3. Checkout the exact trusted main SHA, load a strict canonical bundle, verify
   owner, actor, event metadata, Work Order ID/revision, Capability,
   isolation profile, denied resources, approved SHA and canonical
   `bundle_sha256`. Gate 1 approval provenance **must** be established by
   the trusted dispatch service/owner; this adapter does not infer owner approval
   from a PR or ChatGPT message.
4. Hosted authorization calls GitHub `git.createRef` for
   `refs/heads/plasma-engineering-claims/<work_order_id>/r<revision>`.
   The existing repository Ruleset *Protect PLASMA engineering dispatch claims*
   prohibits update/deletion. Existing ref → non-success → worker skipped.
   Verify Git ref readback before scheduling any worker job. This is an
   atomic **cross-run** replay claim, unlike local runner temp files. An
   unrelated branch mutation or ruleset bypass MUST block activation.
5. Worker receives only the pinned trusted commit and SHA-bound bundle.
   No GitHub write token is persisted. Its check-in, external OS isolation,
   runner identity and job-success dependency are mandatory.

## Physical and privilege isolation: activation blockers

**Prompt restrictions are not kernel isolation.** The current
`SWPC-plasma-codex` is intentionally HIL-capable and MUST NEVER receive
the new `plasma-dispatch-isolated` label.

Before setting the enable variable (requires an **independent approved
activation and operational test plan**):

1. Provision a dedicated non-root
   `SWPC-plasma-dispatch-isolated` runner under an OS account without
   device groups, privileged container/sudo access, Docker socket,
   direct /dev or lab network routes; verify with real OS namespace/ACL/
   firewall probes, not just `id` or a prompt.
2. An independent root provisioner must install a root-owned 0644 (or
   stricter) `/etc/plasma/engineering-dispatch/isolation-v1.json` with exact
   `os_isolated`, `no_hardware_devices`, `lab_network_blocked`
   assertions, **after** verifying enforcement. The worker refuses missing/
   writable/symlink/false attestation, but marker alone is not proof.
3. Verify protected claims Ruleset enforcement, create/readback, replay 422,
   ref immutability and behavior after retries; fail closed for missing
   effective rules or exhausted repository permissions. Do not enable
   `workflow_dispatch` without a verified trusted Gate 1 provenance broker.
4. Supply secure, job-bound Codex authentication and workspace write guards.
   The current worker implementation deliberately does not publish PRs.
   Design a separate trusted, isolated publisher and guarantee new PR CI
   really triggers (default `GITHUB_TOKEN` events may be suppressed).
5. Test liveness/cancellation/timeout behavior, audit evidence retention,
   source path symlink and TOCTOU attacks, network exfiltration guards, and
   worker cleanup. Never use a repository PR to provision a runner.

A successful Gate 1 **offline** CI is not operational readiness. The
enable flag must not be switched on in this PR or from a merged PR.

**Two independent activation interlocks:** GitHub repository variable
`PLASMA_ENGINEERING_DISPATCH_ENABLED=true` **and** checked-in
`specs/engineering-dispatch/runtime-activation-v1.json` status
`ENABLED_BY_SEPARATE_APPROVAL`, with an explicit per-path switch. The latter
is checked by the Python CLI before `authorize` or `worker`. It currently
contains `DISABLED_GATE1` and both paths `false`. Changing only the GitHub
variable cannot permit task execution. The legacy capability policy remains
contract-only: a reviewed runtime policy migration and real isolation
acceptance are still required before production readiness.


## Test contract / status vocabulary

- `RUNTIME_BUNDLE_VALIDATED_NO_EXECUTION`: deterministic offline validation.
- `AUTHORIZED_PENDING_ATOMIC_CLAIM`: hosted authorization preliminary
  result **before** a durable GitHub claim; cannot launch work by itself.
- `WORKER_PASS` / `WORKER_FAIL`: only real isolated worker runs, with SHA256
  of bounded stdout and stderr; no raw secrets should enter receipts.
- `NO_GO_RUNTIME_DISPATCH`: failed admission (no execution).
- `NOT_RUN`: no real worker invocation / missing Gate 1 provenance.

Offline negative tests exercise unauthorized actors, PR/push attempts,
scope/capability escalation, injected shell argv, path traversal,
unreviewed digest, rerun, unknown fields and missing isolation.
They must not invoke Codex, SSH, sudo or any physical HIL fixture.

## Nine-by-nine pilot

PR #1043 already merged the deterministic 81-cell Python reference and hosted
CI test. It is a useful benchmark for a future `path2-cli` Work Order.
**There is deliberately no executable Path 2/3 pilot bundled in this PR**:
the generic dispatcher is not yet activated, and a hosted CI check
must not be misrepresented as SWPC CLI/Codex execution.
