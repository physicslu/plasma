# PLASMA Engineering Runtime Dispatcher v1 — current state and Development Mode gate

**Status:** Qualification `workflow_dispatch` Runtime remains **DISABLED**.
The shared Workflow's owner-only Development Mode `issue_comment` entry is
implemented and has successfully executed real Path 2 CLI and Path 3 Codex
smoke tests on existing `SWPC-plasma-codex` (PRs #1047–#1049). This is not
permission to run other tasks, operate devices, or deploy production Runtime.
See `AGENTS.md` §11.1 and the canonical Three-Path execution model for
approval and evidence requirements.

## Development Branch Dispatch v1 — Gate 1 pre-merge source pinning

**Gate 1 implementation candidate in this PR; no live SWPC confirmation yet.**
The same trusted main `.github/workflows/plasma-engineering-runtime-dispatch.yml`
now supports an owner-authored Issue #981 command for an existing, open,
same-repository, owner-created non-`main` PR, with its **exact current head SHA**:

```text
/plasma-dispatch run <task-id> --pr <number> --sha <full-40-character-commit-sha> 981
```

This is a new branch-mode syntax. The legacy main-only owner command remains
supported without `--pr` and `--sha`. The exact task ID must exist in the
candidate commit's `specs/engineering-dispatch/development-tasks-v1.json`;
the requested Path and relevant command/output contract are validated by
the **main** dispatcher, not by dispatcher Python from the PR.

1. The owner-only GitHub-hosted admission job parses the strict request
   *before* GitHub API access; only approved Issue #981 created comments
   from `physicslu` proceed.
2. It retrieves the live PR metadata using a read-only GitHub token,
   rejects non-open/non-owner/fork/wrong-base PRs and stale or mismatched
   PR HEAD SHA, and checks out the **exact SHA** into a separate `candidate`
   tree without executing that tree's code.
3. Trusted authorization and worker adapter code is always checked out
   from the `main` event SHA under `trusted`. Worker source and registry
   are a separate, pinned candidate checkout. GitHub-hosted authorization
   carries the candidate SHA, trusted main SHA, PR number and registry digest.
   The worker verifies these before invoking CLI or Codex.
4. Path 2 accepts checked-in fixed Python CLI plus expected stdout SHA256,
   uses one task-independent `cpu-only` capability contract and archives
   stdout/stderr and the receipt. There is NO `nine-nine-path2` routing
   exception or `nine-nine-table-v1` validation policy; multiplication tests
   are only ordinary test fixtures. Path 3 delegates the objective to Codex,
   supports creating or repairing the approved Python file, and collects
   the source, text or CSV output (`output_format: text|csv`), self-test and
   Codex session logs. Its reference SHA256 is optional for new unknown-output
   objectives. Only the approved source file may be changed, and its
   tracked diff is preserved in a source patch artifact for review;
   **ChatGPT** reviews evidence, not AST shape or fixed CSV column labels.
5. Both use the *existing* `SWPC-plasma-codex` self-hosted Runner, with
   no new task-specific Workflow. PR/push checks are GitHub-hosted offline
   only. The formal qualification `workflow_dispatch` Runtime stays OFF.

This is **not** blanket trust of PR code: only the owner-authorized exact
same-repository candidate commit enters the existing development workers.
The shared SWPC Linux account is hardware-capable, and prompt restrictions
do not substitute for OS isolation; no hardware operation is authorized by
this feature. PR metadata is checked at hosted authorization time; changes
to a PR after approval cannot silently change the pinned checkout SHA.
The owner must authorize a new full SHA to run a subsequent revision.

**This PR's Gate 1 test evidence is hosted/offline contract and simulated
executor tests only**. Do not call it a real pre-merge SWPC Path 2/3 PASS.
The owner must separately approve Gate 2 before merging this dispatcher
foundation; afterward later task PRs can be executed during their own Gate 1.

## Development Mode capability-based Path 2 routing (AUTO-4)

The Issue #981 owner-only hosted authorizer validates the live OPEN PR,
exact pinned HEAD, candidate registry digest, and a typed execution path.
It emits `execution_capability` from the **trusted main** dispatcher:
`cpu-only` for ordinary bounded Python CLI, `codex-workspace` for Path 3,
and `z2-cpu-only` only for the separately approved main-only HIL-A2 task.
Task IDs are **identifiers**, not permissions. A new CPU-only task must NOT
require a per-task Workflow edit or a reference to the former 9×9 pilot.
Existing bounded development manifest entries without an explicit capability
are treated as CPU-only for compatibility; any unrecognized capability or
attempt to select an HIL capability from a candidate PR is denied.

For CPU-only Path 2, the trusted SWPC Dispatcher requires Linux bubblewrap
(`bwrap`) before executing the PR candidate program. It uses unshared
namespaces (including network), a read-only candidate workspace and OS Python
runtime, a minimal synthetic `/dev`, isolated `/proc`, empty temporary
filesystem, cleared environment and `python -I -S`. No user hardware, USB,
MMIO, SSH agent, host filesystem or network is intentionally mounted. Missing
or unusable sandbox must **fail closed**; no fallback to unsandboxed Python.
A GitHub-hosted unit test checks the constructed sandbox command but cannot
prove that SWPC supports this kernel namespace configuration. The actual
SWPC execution must be confirmed by a separate real Job, including raw
stdout/stderr and Exit Code. This CPU-only Development boundary is not the
independent production Qualification Runtime isolation standard.

HIL-A2 is **not** admitted via the CPU-only branch. It retains the main-only
Work Order, one-shot Claim create/readback, `github.run_attempt==1`, matching
Claim digest and separate hardware approval. No hardware or Qualification
Runtime deployment/activation is authorized by the capability routing change.

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

The task registry is reusable: a reviewed task changes only the registry,
not the GitHub Workflow. Development Mode now supports both the proven fixed
Path 2 CLI and a **bounded Path 3 Codex smoke** on the same existing Runner.

The owner can trigger the Path 3 smoke by posting the exact comment to
Issue #981:

```text
/plasma-dispatch run nine-nine-path3 981
```

The hosted admission checks the same owner/Issue/commit controls. Job
`development-codex` on `SWPC-plasma-codex` runs **real Codex CLI** and
assigns it an outcome, not a prescribed implementation. Codex independently
writes Python source, executes it, verifies all 81 products, and may debug
and rerun. The Dispatcher does **not** parse/limit generated source AST,
re-execute the Python program, or certify that 81 products are correct.
GitHub Actions only checks that the Codex process exited and that the
source, actual CSV, self-test report and Codex session log can be collected.
It archives all four with a JSON **EVIDENCE_READY_REVIEW_REQUIRED** receipt;
this is not an acceptance PASS. ChatGPT examines original code and evidence,
checks the actual products and explicitly reports PASS/FAIL and, if needed,
new Codex instructions. The Path 2 reference SHA256 is a comparison aid,
not a Path 3 Run-side gate, because Codex can choose CSV header labels.

This smoke does not authorize hardware actions, Git push, PR creation or
merge. A full Codex → source PR → CI development loop is a separate test.
Hosted CI may exercise the evidence adapter with a fake Codex, but only
a real SWPC Job and independently reviewed evidence support Path 3 E2E PASS.
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

## Gate 1 before Gate 2: required pre-merge development capability

**Normative Development Mode sequence:** owner's Gate 1 approval → execute
the intended **real** SWPC Path 2 CLI or Path 3 Codex assignment → collect
original logs/source/output/evidence → ChatGPT independent evidence review →
within-Gate-1 repair/retest on FAIL → submit/finish PR and relevant CI →
owner Gate 2 approval **only for Merge**. A successful GitHub Job means the
worker ran; the reviewer decides whether the requested engineering test PASSes.
Path 3's Codex does its own implementation, execution, self-tests and repairs;
the Dispatcher should collect evidence rather than prescribe a Python AST or
independently re-run every Codex program.

**Historical pre-v1 implementation gap (addressed in this candidate PR, pending merge and live validation):** the
Development Mode `development-authorize` and worker use
`GITHUB_REF=refs/heads/main`, `GITHUB_SHA` from that event, and a checked-in
task registry on the default branch. GitHub `issue_comment` loads its
Workflow definition from the default branch. Consequently a new or changed
task defined **only in a PR branch** cannot yet be executed by this current
entry before merge. In the #1048/#1049 smoke development this forced an
undesirable merge-then-test sequence. **Do not repeat that pattern or
misrepresent a hosted/offline CI PASS as SWPC E2E PASS.**

**Minimal next implementation (future independent PR, not done here):**
extend the *existing shared* owner-only Dispatcher to receive a reviewed
development branch or exact commit SHA as the task's execution source,
validate owner/task/ref/repository and relevant GitHub PR/commit provenance,
pin the authorized revision through hosted admission and SWPC checkout, and
run the already-approved real experiment **before** merge. Retain the existing
`SWPC-plasma-codex` Runner, no new task-specific Workflow and no additional
owner gate. The `main` Workflow itself can remain trusted; it must explicitly
permit and validate a task's separate pre-merge source SHA rather than
silently using `main` for both. Until the new branch-dispatch code is merged and proves real SWPC operation, report its current validation boundary accurately; do not bypass guards or merge other task PRs merely to activate their tests.

Gate 2 may exceptionally approve knowingly deferred development evidence
only after the owner sees exactly which acceptance is missing. Such
exceptions do **not** redefine the normal two-gate workflow.

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
| 2 | Fixed CLI | Trusted current main entry → existing shared SWPC Runner | real CLI exit/output evidence, reviewed in Gate 1; PR/Gate 2 only if merging changes |
| 3 | Agentic | Trusted current main entry → existing shared SWPC Codex Runner | Codex-created source, self-test, raw output, ChatGPT evidence review in Gate 1; PR/CI then Gate 2 only for Merge |

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
