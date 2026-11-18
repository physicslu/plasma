# WP-01 pre-submit independence repair — PR #1441

2026-11-15, Path 3, existing `SWPC-plasma-codex`, `workspace-write`.
Input/source HEAD: **`46780bd22a6879b2a9b9e7d9e055b41d3d980ed6`**.
[Owner Work Order](https://github.com/physicslu/plasma/issues/981#issuecomment-6889409937)
SHA256: `13db72b3d831cafdb9e24d57a05d31b62ec9a4d01fda115002afe96fc84064f9`.
The public JSON was re-hashed using the trusted dispatcher's canonical
`json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=False)` encoding;
the digest matches. Root AGENTS, Common, Path 3, Manager, frozen scheduler
architecture/ADR, WP-01 seed scope, unified programming/Retry contracts and
[independent review](https://github.com/physicslu/plasma/pull/1441#issuecomment-6889407275)
were read. This report supersedes the initial implementation's round-robin
independence claim; the earlier report remains historical evidence.

Execution: [run 43678691721 / job 132705390522](https://github.com/physicslu/plasma/actions/runs/43678691721/job/132705390522),
`development-codex`; Python 3.12.13. Trusted `development-authorize` job
132705353285 was observed completed/success. The engineering job was still
in progress when checked; its later outcome is not asserted here.

## Repair and boundaries

One canonical Manager Batch/Plan/Start/Run/Job engine remains. Its existing
maximum Target Set of 64 Sites bounds a `ThreadPoolExecutor`, with one outstanding
advance per Site lane. Blocking readiness, planning, Start/spawn and status work
can proceed independently. Every lane is initially submitted; completed advances
are rescheduled without waiting for a slow peer. These host workers do not set
PPU hardware capacity or change installation defaults.

Batch specification/commissioning/token checks and durable acceptance precede
remote readiness. Initial Platform admission runs once per PPU, shared only by
that PPU's Sites; Site readiness runs independently. Execution/retry readiness
is rechecked. A remote shared-control admission failure now leaves a consumed,
reconcilable Batch with SHARED_CONTROL_FAILURE rather than making the entire
Batch request synchronously wait for every readiness response. A known shared
latch still refuses subsequent Batch requests before acceptance. Request/response
schemas and the sole Manager-issued Start identity are retained.

All Batch state/journal writes and new dispatch reservations use the Batch lock.
The durable `planned` and `starting` boundaries remain before Start; the lock
is released before Start/spawn can block on HTTP. StopQueuing prevents later
reservations; an already committed reservation is possibly sent and is observed,
never claimed cancelled. Shared worker, scheduler and journal failures publish
the global latch before waiting for slow work to drain. Already accepted Runs
are observed; PPU UNKNOWN still prohibits new submissions on that PPU, with no
blind resend and no fabricated terminal receipt. Other PPUs may continue.

A delayed readiness HTTP response can arrive after a compatible peer acquired
the PPU lease. Readiness therefore carries the exact admitted Batch owner even
before its first Run is active. Foreign owners, same-Site overlap, incompatible
Resource/Image/Active Set identities and exclusive activation remain refused.
A dedicated lock makes pure local Bundle computation/cache insertion atomic;
no remote planning call executes under that cache-build lock. Standalone and
single-Site Flash retain their canonical workflow and default owner behavior.

Changed code/tests: `programming_batch.py`, `programming.py`,
`test_programming_batch_lanes.py`, `test_programming_batch_targets.py`,
`test_programming_batch_coordinator.py`. The immediate-terminal fake Gateway
now retains independent Job IDs/receipts under concurrent calls. Prior tests
that assumed a serial order use events to establish Stop, UNKNOWN, threshold
and fault causality. Two evidence Markdown files are also changed/added.
No Repeat >1, MES, UI, Z2 configuration or additional programming executor.

## Observed acceptance

All commands below run from the repository root with
`PYTHONPATH=software/python` and
`/tmp/plasma-ppu-trust-gate1a-venv/bin/python`.

Final regression, **exit 0: 307 passed in 8.08s**:

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

Log: `.plasma-path3-evidence/wp01-presubmit-regression.log`.
Includes E/P/V, legacy single-Site Flash, retries/SAFE_OFF, Stop, exact identity,
owner/resource incompatibility, restart and Start/journal rollback regression.

Original focused 22 cases, **exit 0: 22 passed / 7 deselected in 1.50s**:

```sh
PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q \
  software/python/tests/test_programming_batch_lanes.py \
  -k 'not pre_submit and not slow_platform'
```

Expanded focused suite, **five invocations**, each **exit 0, 29 passed**
(2.13s, 2.13s, 2.09s, 2.18s, 2.09s):

```sh
PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q \
  software/python/tests/test_programming_batch_lanes.py
```

Log with each exact command/exit: `.plasma-path3-evidence/wp01-presubmit-focused.log`.
The seven added cases hold actual fake Gateway HTTP in readiness, Plan or
synchronous Start pre-submit execution, both across PPUs and on independent
Sites of one PPU, plus held Platform admission on one PPU. Events require the
healthy Site's POST and accepted Run before releasing the blocked HTTP. There
are no latency/sleep guesses; held calls have a 10-second test watchdog. Existing
2/8-Site POST barriers require overlap before terminal release and exercise
concurrent durable updates, same-Site exclusion, accepted Jobs during Stop,
UNKNOWN isolation/no resend, shared failure, Retry SAFE_OFF and sealed Sites.
These are fake PPU observations, never physical programming evidence.

Negative control, **expected exit 1: 1 failed / 28 deselected in 10.23s**:

```sh
PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q \
  software/python/tests/test_programming_batch_lanes.py \
  -k 'pre_submit and False and plan'
```

For this command only, `_run_units`'s concurrent dispatch loop was temporarily
replaced with the input SHA's original `while lanes` round-robin walk. The new
initial-admission setup and generator arguments were retained so the failure
was specifically serial dispatch, not a signature mismatch. Failure:
`healthy POST must precede slow lane release`. A Python `finally` restored the
candidate immediately, before final positive tests. Log:
`.plasma-path3-evidence/wp01-serial-negative.log`.

Socket integration attempted again on the final source, **exit 1**,
**11 passed / 9 failed / 2 setup errors**:

```sh
PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q \
  software/python/tests/test_ppu_execution_ownership.py \
  software/python/tests/test_runtime_activation.py \
  software/python/tests/test_manager_readonly_contract.py
```

The nine failed cases (five ownership TCP, four runtime-activation Unix) and
two read-only HTTP setup errors were denied local socket creation:
`Operation not permitted` / `could not bind ... 127.0.0.1:0`.
Their intended integration behavior is **NOT_RUN**, not PASS. Log:
`.plasma-path3-evidence/wp01-presubmit-sockets.log`.
No privilege/sandbox/service changes or permission workaround was attempted.
The resolution is required CI or an authorized socket-capable test environment.

`git diff --check`: **exit 0**. Intermediate runs found real cache/owner races
and serial-order test assumptions; these were repaired before the final runs
above. No unexecuted test is reported PASS.

## Publication and remaining blockers

PR #1441 was observed **open/Draft**, head exactly equal to the input SHA.
The current trusted workflow explicitly requires this candidate HEAD to remain
uncommitted and performs collection/publication **after Codex exits**, in
`.github/workflows/plasma-engineering-runtime-dispatch.yml` steps
`Collect Path 3 evidence...` and `Publish successful Path 3 edits...`.
Accordingly these changes are left uncommitted for that same-PR publisher;
no competing commit/push or credential route is used. The test logs are under
`.plasma-path3-evidence` for its separate engineering-evidence archive, excluded
from source publication. This tracked report accompanies the source diff.

**Publication, artifact upload and resulting PR HEAD: PENDING at author time.**
The publisher must report its new commit SHA; final-HEAD hosted CI, including
the denied socket tests, is **NOT_VERIFIED** until actual checks execute on
that SHA. A successful Codex/publisher wrapper is not hosted CI acceptance.
Independent post-publication review and the #1439 documentation dependency
remain outstanding. No Gate 2 readiness or full acceptance is claimed with
these items outstanding. PR remains Draft; **Gate 2 NOT_GRANTED**.

SWPC services, deployment/restart, credentials, SSH/USB/TTY, privileged actions,
Z2/FPGA/DUT and electrical/power/hardware validation: **NOT_RUN**. No merge or
auto-merge. There is no observed physical safety/recovery claim.

## Tested source identity

These hashes identify the tested candidate content independently of the later
publisher commit metadata:

```text
22e6d418ba185eda64cbac8094a1433d56f1ab58e2b20f19cc5429cffcefcf08  software/python/plasma_manager/programming.py
38d888ccde4a797d36301a9222d1a3b7829b056c072d063b63c922899da1feba  software/python/plasma_manager/programming_batch.py
ff1cb0d8e4cf30d7e8306e18e8c8df60959e01e5ee872bc7c47ab1bc4fff18d7  software/python/tests/test_programming_batch_lanes.py
f0db37747c9bf2631eeda0f0b88ca007c419d57a08ad0187fd8f8a1197978a34  software/python/tests/test_programming_batch_targets.py
5ca1db337a9313346677c5b4bc9b79dec0c8efa9e65490281c6c34c7fd01b12e  software/python/tests/test_programming_batch_coordinator.py
```

Model/request/token billing metrics are unavailable in this engineering
session; no subscription allowance inference is made. Wrapper telemetry is a
separate source, not functional acceptance.

## Independent post-publication reconciliation (2026-11-15)

The trusted Path 3 follow-up [run #43678691721](https://github.com/physicslu/plasma/actions/runs/43678691721) **completed SUCCESS**: owner authorizer job `132705353285` SUCCESS and `development-codex` job `132705390522` SUCCESS. The job log shows `PATH3_AUTHORIZED_PR_PUBLISHED` and a normal non-force push. The source-and-test publication commit is **`6112bad3660c41002c0e2ddcc2ea015892074d89`**, 7 changed files. The original `PENDING` note above is the worker's earlier observation, not the final result. The publisher artifact `plasma-development-codex-43678691721` ID `14148445330` was uploaded.

**Hosted CI admission:** GitHub created 13 PR workflows for the bot-published commit but returned `action_required`, with no test jobs executed. A subsequent owner-linked commit appending this reconciliation aims to trigger eligible Hosted CI; the exact resulting HEAD and completed CI must be checked separately before Gate 2. The worker's **307-pass** selected Host-only regression and **29-pass × 5** focused runs remain valid only for the tested source hashes recorded above.

**Independent contract-review concern:** `docs/architecture/unified-programming-architecture-v1.md` §5.3 distinguishes invalid/unauthorized admission refusal from target readiness and preserves Start reconciliation. The initial `programming_batch.py::_start` previously read Platform admission before consuming the Start. In the new pre-submit isolation design, some Platform shared-control failures are detected **after** the Batch has been journalled and `start_id` consumed, changing the observed HTTP/refusal/reconciliation behavior tested in `test_programming_batch_targets.py`. Although all new paths fail closed for submission, the external contract compatibility has **not** been independently approved. Require a narrowly scoped compatible correction or an explicit source-backed architecture decision before Gate 2; do not silently relax the previous semantics. No production equipment operations or merge are authorized.
