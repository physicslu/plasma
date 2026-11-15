# WP-01 initial admission compatibility — GAP, Gate 2 NOT_READY

2026-11-15. Path 3, existing `SWPC-plasma-codex`, `workspace-write`.
Input HEAD: `5e942940bdd055ecba89bf62872973d631696099`, clean at entry.
PR [#1441](https://github.com/physicslu/plasma/pull/1441) was open/Draft at that exact HEAD.
Executor: `development-codex`, [run 43681057215](https://github.com/physicslu/plasma/actions/runs/43681057215).
Owner [Work Order](https://github.com/physicslu/plasma/issues/981#issuecomment-6889735215)
was read and its JSON rehashed with the trusted canonical encoding:
`json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=False)`.
SHA256 **`b3f082f2ea1697c0713da9eeda840c4b9723659e2f82d84d7aea8ae023c46869`** matches.
Root AGENTS, Common, Manager, Path 3, unified architecture §5.3/5.7,
frozen scheduler contract and [owner review](https://github.com/physicslu/plasma/pull/1441#issuecomment-6889732432) were read.

## Finding and bounded disposition

**Confirmed external admission/reconciliation compatibility regression. No compatible
implementation satisfies both requested properties under the existing synchronous
whole-Batch admission API. Publish this Gap report only; do not change runtime,
contract, or tracked tests.** Existing green tests do not resolve the conflict.

Historical source and original tests were read from exact pre-repair commit
`46780bd22a6879b2a9b9e7d9e055b41d3d980ed6` through GitHub raw file reads:
`software/python/plasma_manager/programming_batch.py` and
`software/python/tests/test_programming_batch_targets.py`.
The original admission tests require `ProgrammingError` 503 and an empty Batch
store. The pinned source rewrites those assertions to require an accepted Batch
with `SHARED_CONTROL_FAILURE`. This changes more than execution order.

The baseline `_start` reads Platform once per PPU and Site readiness per Site
before `consume_batch_start`. A shared failure publishes the control latch and
raises 503 before admission. The pinned `_start` validates specification,
commissioning and token, consumes the Start, persists the Batch and spawns lanes;
initial remote readiness runs in `_run_attempts` afterwards. The canonical HTTP
handler returns 202 whenever `start_batch` returns, including an already terminal
shared-failure Batch. It cannot retrospectively change a response or unsubmit a Job.

## Observed before/after request and recovery effects

The probe uses `with_start(workflow, [one('z2', 2)])`: a fresh Manager-issued
`start_id`, the existing STM32 ICPN fixture, `operations=[erase,program,verify]`,
`image_base64` of the existing image fixture and `image_filename=app.bin`.
Both classified `SHARED_CONTROL_FAILURE/AUTHORITY_CONTROL_UNUSABLE` and a
Platform `RuntimeError` are injected separately at the initial gate.
The real canonical POST handler and `_programming_call` are invoked directly,
capturing their `_json` status/payload. This tests HTTP status selection without
opening a socket; network transport is NOT_RUN in this probe.

| Observation | Baseline coordinator | Pinned coordinator |
| --- | --- | --- |
| First POST result | 503 `manager_shared_control_failure` | 202 accepted Batch, shared failure recorded |
| Start journal record | ISSUED, unchanged bytes | CONSUMED, linked to Batch |
| Batch journal | unchanged bytes, no admitted Batch | persisted Batch with same Start and Target Set |
| Start reconciliation | ACCEPTANCE_PENDING / START_STILL_ADMISSIBLE | TERMINAL_CONFIRMED, Batch shared-failure evidence |
| Token still startable by token validation | yes (global shared latch still refuses dispatch) | no |
| Repeating same POST with shared latch present | 503, still no Batch | 503, still exactly one Batch |
| Job submissions | zero | zero |

An unconsumed ID is **not** immediately `NOT_ACCEPTED`: reconciliation truthfully
returns ACCEPTANCE_PENDING while it remains admissible. Neither HTTP failure
nor a healthy idle PPU proves NOT_ACCEPTED. On the pinned code the shared latch
takes priority over the duplicate-token 409; do not tell clients this repeat
necessarily returns 409. A normal all-readiness-BLOCKED Batch instead returns
202, consumes the ID and refuses its repeated Start with 409.

Separate unknown and uncommissioned Target probes refuse before consumption,
leave no admitted Batch and submit no Job. A valid Target with Platform BUSY is
admitted BLOCKED, consumes the Start and submits no Job. These cases must stay
distinct from failure of the shared machinery judging readiness.

## Causality conflict and proof

Let A's initial Platform gate be held at an event, and let B be healthy on a
different PPU. Until the event is released, two executions are indistinguishable:
A will eventually return READY, or A will return SHARED_CONTROL_FAILURE.

Historical refusal requires every initial verdict before admission: if A returns
shared failure, no Batch/Start consumption or Job submission may have occurred.
Pre-submit independence requires B's Job POST **before A is released**. Such a
POST requires durable admission and submission intent first. At that point the
shared-failure execution can no longer satisfy historical refusal. Waiting to
send the HTTP answer does not undo the committed Start/Batch/Job. Consuming and
later rolling back is unsafe for reconciliation and journal-before-submit.

The event-controlled late-failure probe exercises this exact counterexample on
the pinned code: A's gate enters and waits; B's actual fake Gateway POST occurs
while A is held; the Start is already CONSUMED; A then returns a classified shared
failure; B's one accepted Job is observed, A submits none, and the Batch records
SHARED_CONTROL_FAILURE. This is a host-only fake PPU observation, not hardware.

Parallelizing initial checks and awaiting all results preserves historical 503
but still blocks B behind a slow A. A timeout, cache, second preliminary check,
or snapshot cannot prove an unresolved remote verdict without changing its
authority/freshness semantics. Returning 503 after B was submitted would falsely
claim non-admission; resetting the token risks duplicate execution. Narrowing
unknown shared failures into local readiness would violate §5.7.

This impossibility concerns an **unresolved initial gate with authority to refuse
the whole Batch**. Slow execution-time readiness, Plan and Start after a completed
admission barrier can be independently scheduled. Same-PPU initial Platform
readiness is inherently shared; Site-specific readiness remains Site-scoped.

## Owner decision required (options, none implemented)

1. Preserve synchronous admission/refusal: retain an all-initial-gates barrier,
   then independently schedule admitted Site lanes. Explicitly amend WP-01's
   acceptance requirement for healthy POST before release of an initial gate.
   This preserves historical refusal but cannot claim that isolation test PASS.
2. Approve durable asynchronous admission semantics: validity-only acceptance
   consumes the ID and returns a reconcilable Batch; later shared failures latch
   new dispatch, preserve accepted Jobs and remain globally classified. This
   explicitly changes refusal, journal and recovery semantics. The pinned code
   approximates this option but is **not owner-approved contract compliance**.
3. Redesign the gate boundary/API through an owner ADR: prove a bounded local
   shared-control admission decision and separately classify remote readiness,
   with explicit authority, freshness, failure-domain and client recovery rules.
   Merely moving a call or renaming its failure does not establish that proof.

An owner-approved ADR/change-control decision must identify the selected tradeoff,
update §5.3/5.7 and WP-01 acceptance where applicable, define status and Start
reconciliation/replay behavior, and migrate producers, consumers, docs and tests
in the same bounded change. No version or new endpoint is authorized here.
Until then retain original test expectations as the historical contract oracle;
do not accept rewritten expectations as a signed amendment. PR remains Draft.

## Executed host-only evidence

All commands ran from repository root with Python 3.12.13. Reproduction scripts,
materialized baseline snapshots and bounded test logs are archived under
`.plasma-path3-evidence/`, excluded by the existing trusted source publisher.
The original snapshots are loaded as separate modules; production files are never
replaced. Baseline-coordinator probes share the pinned workflow and fake fixture,
so they isolate coordinator admission behavior rather than claim a full historical
checkout regression. The historical test functions retain their original bodies.

```sh
PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q -s /tmp/test_wp01_admission_gap.py
# exit 0: 8 passed in 0.30s

WP01_BASELINE=1 PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q /tmp/test_wp01_historical.py
# exit 0: 3 passed in 0.20s (original authority/policy/exception expectations)

PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q /tmp/test_wp01_historical.py
# expected negative-control exit 1: 3 failed in 0.25s, DID NOT RAISE ProgrammingError

PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q software/python/tests/test_programming_batch_lanes.py
# exit 0: 29 passed in 1.93s

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
# exit 0: 307 passed in 8.88s

PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q \
  software/python/tests/test_ppu_execution_ownership.py \
  software/python/tests/test_runtime_activation.py \
  software/python/tests/test_manager_readonly_contract.py
# exit 1: 11 passed, 9 failed, 2 setup errors in 1.02s
```

The 29 focused cases retain cross-PPU and same-PPU held readiness/Plan/Start
proofs, healthy POST before slow release, slow Platform isolation, 2/8-Site
overlap, Stop, shared latch, PPU UNKNOWN/no resend, journal crash boundaries,
same-Site exclusion, owner/resource/image identity, SAFE_OFF and sealed Retry.
Broader selected regression covers single-Site workflow/legacy Flash, Start/Run
identity and journal rollback. It is not a claim that real single-Site Flash ran.
Green pinned expectations do not override the three failing original oracles.

The socket suite was actually attempted, with no exclusions from its command.
Its five ownership TCP tests and two read-only HTTP setups could not bind/create
loopback sockets; four runtime-activation tests could not bind Unix sockets
(`PermissionError: Operation not permitted`). Those eleven integration behaviors
are **NOT_RUN**, not product FAIL or PASS; eleven other cases passed. No sandbox,
service, privilege or device workaround was attempted. Exact case names and
tracebacks are retained in `wp01-admission-sockets.test.log`.

An initial probe run exited 1 (2 failed / 6 passed): it incorrectly assumed no
Batch journal file existed after coordinator initialization. Corrected to compare
the initialized journal bytes before/after; initialization creates an empty
journal and refusal leaves it unchanged. No production expectation was changed.

## Source identities and publication

SHA256 of tested unchanged source / materialized evidence:

```text
22e6d418ba185eda64cbac8094a1433d56f1ab58e2b20f19cc5429cffcefcf08  software/python/plasma_manager/programming.py
38d888ccde4a797d36301a9222d1a3b7829b056c072d063b63c922899da1feba  software/python/plasma_manager/programming_batch.py
d274bc134bbcf4ba2577fac9b81c4761c209c94424e34d730a93d12899d934e8  software/python/plasma_manager/bootstrap_server.py
ff1cb0d8e4cf30d7e8306e18e8c8df60959e01e5ee872bc7c47ab1bc4fff18d7  software/python/tests/test_programming_batch_lanes.py
f0db37747c9bf2631eeda0f0b88ca007c419d57a08ad0187fd8f8a1197978a34  software/python/tests/test_programming_batch_targets.py
bc270fae0aa35997b41b7bde60da3586a44f79ae33fa7632c7337df213e27794  wp01-baseline-programming_batch.py
17c34290733756f4d2d6a5db395608ab4a22103caf4e74dcd640311fcb078173  wp01-baseline-test_programming_batch_targets.py
024acf55868b7881f62234204af01ab317833a37ba5833c4513a8c7fd4f4ee27  test_wp01_admission_gap.py
eb2b0ea785247802297efa2b3d2c34619d942cd3723f2e4214b64b9ffbcb8d57  test_wp01_historical.py
```

Only this Gap report is a source-publication change. Candidate HEAD remains
uncommitted at the pinned SHA, as required by the existing workflow's `Collect
Path 3 evidence` / `Publish successful Path 3 edits to the exact authorized PR`
steps. The publisher runs **after this agent exits** and checks the unchanged PR
HEAD before a normal non-force push. No competing commit/push or GitHub write
route is used. Publication/new final PR HEAD and that HEAD's hosted CI are
**PENDING / NOT_VERIFIED at report time**; they cannot be observed in advance.

A bounded GitHub API observation on the input SHA found 13 hosted workflows:
11 completed/success; Python PS source tests run `43681014021` and Control Station
runtime packaging run `43681013923` were in progress. Check-runs: 17 success,
1 skipped domain-boundary job and 4 in progress. This is not final-HEAD CI PASS.
The current engineering run is also not yet complete while this report is written.

**Remaining blocker:** explicit owner ADR/scope decision above, then bounded
implementation and acceptance, trusted publication, exact-final-HEAD CI and
independent review (including #1439 dependency) before Gate 2 can be considered.
No merge approval granted, no ready-for-review transition, no merge/deployment.
SWPC services, Z2, FPGA, DUT, credentials, privileged operations and physical
Flash/electrical SAFE_OFF/HIL: NOT_RUN. No new physical safety/recovery claim.
Model billing/token metrics are unavailable here; no subscription inference.
