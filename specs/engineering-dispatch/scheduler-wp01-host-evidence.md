# WP-01 Host-only engineering evidence — PR #1441

> Follow-up pre-submit repair and current evidence: [WP-01 pre-submit independence](scheduler-wp01-presubmit-evidence.md). The initial round-robin implementation described below did not isolate blocking admission/Plan/Start; see the follow-up for its replacement and remaining CI/publication obligations.

Date: 2026-11-15. Path 3, existing SWPC `SWPC-plasma-codex` worker,
`development-codex`, Python 3.12.13 / pytest 9.2.0, workspace-write.
[Actions run 43676267155 / job 132697029714](https://github.com/physicslu/plasma/actions/runs/43676267155/job/132697029714).

Input/source HEAD: `d930fcaace6d2043221762627cabba97398f5e47`.
Owner dynamic Work Order SHA256: `999c2db4190283bfdd84305c406d65692dff63eb962b8ec3b1a516145b32de09`.
The trusted authorizer job `132696994169` was observed successful. This digest
identifies the dynamic owner Work Order, not the seed Markdown scope file.
Root AGENTS, Common, Path 3, Manager and Embedded contracts, the pinned seed
scope, accepted frozen design and Issue #1440 were read. Only WP-01 is implemented.

## Implemented behavior

- The existing canonical Batch engine advances bounded Site lanes round-robin.
  It yields while each ordinary workflow Run is active, rather than waiting for
  that Site before submitting healthy peers. The Target Set's existing limit
  is 64 Site lanes; actual execution remains subject to PPU admission and its
  configured semaphore. No second executor, Repeat engine or new endpoint.
- Batch-issued Runs carry the existing Gateway REST execution owner ID. The
  workflow permits distinct Sites under that exact owner only with matching
  verified Resource, Image and Active Set identities. Resource activation stays
  exclusive. A standalone Run and the legacy single-Site Flash path retain
  their existing admission behavior.
- Journal mutations and Stop/Start admission share locks. Attempts record a
  durable `starting` boundary before invoking Start. A missing Run answer at
  that boundary remains UNKNOWN after restart, including a PPU latch derived
  from the Batch if its Run is missing. No automatic resend or reconciliation
  acknowledgement is introduced.
- Manager control/journal failure stops new submissions globally. Already
  committed submissions remain possibly sent; accepted Runs are observed,
  never fabricated as cancelled. Affected PPU UNKNOWN remains PPU-wide while
  independent PPUs can continue. Journal retention preserves active and UNKNOWN
  evidence; this is not long-run Repeat/Work Order retention qualification.
- Retry still requires a definite terminal receipt, exactly one Job submission,
  matching identities, SAFE_OFF and fresh readiness. Each retry uses a new
  plan/Run/Job. Stop thresholds and StopQueuing precede any further attempt.
- The prior restart test now expects all three lanes that crossed Start to be
  UNKNOWN, rather than assuming the former sequential execution order.

Changed production/test files: `software/python/plasma_manager/programming.py`, `software/python/plasma_manager/programming_batch.py`,
`software/python/tests/test_programming_batch_targets.py`, `software/python/tests/test_programming_batch_lanes.py`. This report is the only additional tracked file.
No UI, Manual Repeat, MES, installer concurrency, device or service changes.
The existing public Batch/Start/Run request contracts and journal schemas are
retained; the internal owner and `starting` bookkeeping are additive.

## Observed verification

Final relevant host regression command, from repository root:

```sh
PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q \
  software/python/tests/test_programming_batch_lanes.py \
  software/python/tests/test_programming_batch_coordinator.py \
  software/python/tests/test_programming_batch_targets.py \
  software/python/tests/test_bundle_programming_workflow.py \
  software/python/tests/test_programming_start_reconciliation.py \
  software/python/tests/test_programming_start_journal_rollback.py \
  software/python/tests/test_manager_server_persistence_wiring.py \
  software/python/tests/test_manager_persistence_schema.py \
  software/python/tests/test_manager_config_compat.py \
  software/python/tests/test_manager_transport_state.py \
  software/python/tests/test_manager_ps_only_topology.py
```

Exit **0**, **300 passed in 8.74s**. Log:
`.plasma-path3-evidence/host-regression-final.log` (Actions evidence artifact).
This includes existing E/P/V and legacy Flash, Retry/Stop, receipt checks,
Start reconciliation/rollback, journal migration and Manager persistence tests.

The new event-controlled file contains **22 tests**. The final file was run
five consecutive times using the same Python/PYTHONPATH and
`-m pytest -q software/python/tests/test_programming_batch_lanes.py`:
all five invocations exit **0**, **22 passed** each. Log:
`.plasma-path3-evidence/host-lanes-repeat.log`.

Overlap assertions require every 2/8-Site POST event before any terminal
release; a serial walk cannot pass. A terminal Barrier releases simultaneous
updates. Tests also cover a held slow Site, independent definite FAIL, same-Site
and duplicate admission, fresh-identity Retry while a peer stays held, mismatched
owner/Resource/Image and activation refusals, UNKNOWN PPU isolation/no resend,
global shared failure, batch/run journal failure, Stop during planning and with
accepted Jobs, concurrent failure thresholds, missing SAFE_OFF, Sealed Sites,
restart at planned/starting boundaries and persisted final outcomes. All are
Host-only fake PPU/Gateway observations, not physical programming receipts.

`git diff --check`: exit **0**.

Additional attempted regression commands were **not green**:

1. Four core modules above plus `test_ppu_execution_ownership.py` and
   `test_runtime_activation.py`: exit **1**, **252 passed / 9 failed**.
   Five ownership tests could not bind `127.0.0.1:0`; four activation tests
   could not bind Unix sockets (`PermissionError: [Errno 1] Operation not
   permitted`). Their intended socket integration behavior was **NOT_RUN**.
2. The broader host regression list plus `test_manager_readonly_contract.py`:
   exit **1**, **295 passed / 2 setup errors** from the same sandbox socket
   denial. Log: `.plasma-path3-evidence/host-regression.log`.

The final green command excludes those socket-dependent modules; it is not a
claim that they passed. No sandbox bypass, service change or privilege change
was attempted. The least restrictive resolution is ordinary hosted CI or an
authorized host-test environment that permits ephemeral local sockets.

## Publication and remaining acceptance

The PR was re-read and remains open/Draft at the exact input SHA. The trusted
workflow requires the candidate checkout to remain **uncommitted** at that SHA
and publishes its diff only after Codex exits successfully (workflow collection
and publication steps). At observation, publication and artifact upload were
pending. This session therefore leaves changes for that publisher; it does not
preempt the publisher or claim its future commit exists.

An attempt to post the evidence directly as a PR Conversation comment was
**NOT_POSTED**: the GitHub connector returned `MCP tool call requires approval,
but approval policy is never`. No alternative credential route or permission
bypass was attempted. This tracked report carries the evidence into Draft PR
#1441 through the already-authorized trusted source publisher instead.

**Final published PR HEAD: NOT_YET_AVAILABLE. Final-HEAD hosted CI,
Rulesets/Reviews/Threads/Mergeability and independent review: NOT_VERIFIED.**
The publisher/reviewer must record the resulting exact SHA, compare the four
source/test hashes below, run required CI including socket integrations, and
attach that evidence to #1441. `GITHUB_TOKEN` pushes may not automatically
trigger PR CI; successful publication alone is not CI acceptance. No full
Gate 1 completion or Gate 2 readiness is claimed while these remain pending.

**Physical HIL, Z2/FPGA/DUT/USB/TTY, electrical/power, deployment/restart: NOT_RUN.**
No PR merge or auto-merge. Gate 2 remains owner approval of a specific
merge-ready HEAD after outstanding acceptance and independent review.
No observed hardware safety/recovery state is asserted by these host tests.

## Tested source/test identity

These hashes identify the tested uncommitted candidate independently of the
publisher's later Git commit metadata:

```text
648540199ba3a9b3b2664020312671ab9545d8b724b43e2270df5eab777a7c57  software/python/plasma_manager/programming.py
ce45471324a7f512c53fa1a908a7cbcf0c38a594f59e7c06f755f350bd5fb574  software/python/plasma_manager/programming_batch.py
050f617c4371e71d40282544fa0913073404efc9dd2614cf577a6e15bdeb3535  software/python/tests/test_programming_batch_targets.py
ef4ad9f64947941af94fa0c38423c92c92adb11bb98fa2e198e5c2ba5b0fb4bd  software/python/tests/test_programming_batch_lanes.py
```

Model/request/token and subscription-allowance metrics are not available to
this session; no usage or billing inference is made. Wrapper telemetry is a
separate evidence source, not functional acceptance.

## Post-publication independent check (2026-11-15)

The trusted Path 3 Publisher **did complete** after the above author-time observation. GitHub Actions [run #43676267155](https://github.com/physicslu/plasma/actions/runs/43676267155), job #132697029714, concluded **success**. The trusted run log observed `PATH3_AUTHORIZED_PR_PUBLISHED` and a normal non-force push to the reviewed PR branch. The resulting tested-source publication commit is `bddf79bd05ae3674912aca71f358b0444561ba99` (5 files: two Manager modules, two tests, this evidence). The successful run proves execution/publication, not physical qualification.

For that published commit, 13 GitHub Actions workflow runs initially returned `action_required`, and their jobs had not run. **This is a workflow-admission state, not a failed test result or a CI PASS.** The owner-linked GitHub commit that adds this post-publication evidence is intended to trigger a fresh eligible PR check; its exact resulting HEAD and actual completed outcomes must be checked separately. Do not infer acceptance from this note.

Outstanding: GitHub-hosted exact-HEAD tests (including socket-dependent suites), independent concurrency/lock review, and contract PR #1439 merge dependency. Current source still supports only `repeat=1`; Manual Repeat/MES remain outside WP-01. HIL / deployment: NOT_RUN. Gate 2 remains NOT_GRANTED.
