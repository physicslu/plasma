# WP-01 option 3 corrective implementation — PR #1441

2026-11-15. Path 3, `workspace-write`, actual Runner `SWPC-plasma-codex`,
executor/job `development-codex`, [run 43697191800](https://github.com/physicslu/plasma/actions/runs/43697191800).
Input and still-uncommitted candidate HEAD: **`993c10f0fea2ccec82cd4ff8609e8b850037a532`**.
Owner [Work Order](https://github.com/physicslu/plasma/issues/981#issuecomment-6892041772)
SHA256 **`98305def0098f27f9795060278c2f7a74081530785a19524c5a97373973b6d7d`**:
recomputed from event JSON with sorted keys, compact separators and
`ensure_ascii=False`; MATCH. Event owner `physicslu`, source SHA and PR match.
Root AGENTS, Common, Path 3, Manager, unified architecture §5.3/§5.7,
owner split contract, source-gap report and unchanged five-case probe were read.

**Production corrective implementation completed with passing host-only checks;
full integration acceptance and final publication/CI remain unverified.** This
supersedes the previous report's NOT_IMPLEMENTED disposition for these fixes.
The PR must remain Draft pending the unresolved acceptance/review below.

## Source decisions and resulting behavior

| Source boundary | Implemented judgement and falsifiable evidence |
| --- | --- |
| `bootstrap_server.py:shared_control_gate`, `bootstrap.py:shared_control_check` | Local-only G0 checks registry enumeration and matching coordinator authority, live poller health, credential-store reads, global Bootstrap transport policy and Cloudflare identity configuration. No client construction, Bootstrap status, remote request or fleet snapshot/observation is performed in G0. A test makes client construction fail while G0 still passes, demonstrating the separation. Failures before admission return historical 503 `manager_shared_control_failure`, no consumed Start, Batch journal delta, Run or Job. |
| `poller.py:shared_control_check` | Requires a running poller thread, no stop request, initialized structurally usable cache and no failed shared refresh. A non-null stopped poller fails. Per-PPU transport failures are already observation values from `FleetAggregator._poll_one`; a source/observation/persistence refresh exception is unclassified shared failure. No arbitrary age timeout or deployment prerequisite was introduced. |
| `bootstrap.py:_entry`, `_live`, `_authenticated`, `status` | Shared registry/credential reads and local endpoint/client configuration run inside named `shared_boundary` contexts. A `PPUTransportError` raised by local client construction becomes shared; the same type raised by actual remote status remains local. Expected missing per-alias enrollment stays a local refusal. Unknown-origin exceptions fail closed. |
| `client.py:_cloudflare_access_headers` | All three identity variables absent means optional/unconfigured. Any configured variable requires a complete valid identity, even if the current endpoint differs. Invalid/incomplete Manager identity raises `SharedControlError` at its actual configuration source, before network I/O; a valid identity is sent only to its exact protected origin. |
| `bootstrap_server.py:platform_gate_reason` | Runs shared check, then independent G1. Programming-only strict cached-state access marks local cache exceptions shared instead of inheriting the generic Handler's swallowed `RuntimeError`. Other Bootstrap HTTP surfaces retain their existing policy helper. Known remote failures stay `TARGET_STATE_UNAVAILABLE`; unknown failures stay shared. |
| `programming.py:target_block`, `_gateway_get`, `_ppu_resources` | Site gate preserves shared provenance; it no longer makes every exception local. Gateway configuration is marked local/shared before remote GET. Known remote read/invalid JSON errors have explicit `_StepFailure.failure_domain`; an unknown Plan state-read exception propagates instead of becoming a local Resource refusal. |
| `programming_batch.py:_start`, `_dispatch_block`; `programming.py:start`, `_submit_once` | Synchronous G0 before token consumption; same authority checked at reservations, Start and pre-POST durable submission. Malformed shared-check verdicts fail closed. A detected dispatch failure publishes the workflow latch while holding the dispatch lock. A previous workflow shared latch also refuses a new Batch before consuming its token. Network calls remain outside shared locks. |
| Batch lane completion / `_shared_failure` | Accepted Jobs retain real results and reconciliation. Globally refused, provably unsubmitted work stays unexecuted, including a Run refused at pre-POST. Possibly sent work retains UNKNOWN; no resend or cancellation is manufactured. Terminal lane classification cannot race an already published global latch into a fictitious local BLOCKED result. |

There remains one canonical Batch → Plan → Start → Run → Job path and existing
wire endpoints/status codes. No Repeat/MES/UI, capacity adjustment, deployment,
service restart or hardware work. Independent Site/PPU workers and exact
owner/Resource/Image/Active Set guards remain in use.

## Journal fault and historical test repair

The old journal test replaced `_persist_locked` itself and failed on the fourth
write. With concurrent lanes, write count did not identify which Site/boundary
failed, and the injected exception bypassed the real journal failure latch.
A peer could therefore finish local classification during the artificial latch
gap. The test now injects device-full at `_write_journal_locked` under the real
latching wrapper, specifically on z2's durable `starting` boundary, and holds
peer readiness with an event until that fault. Production terminal classification
also consults the global latch before accepting a lane's local result.
No outcome/zero-peer-POST assertion was weakened. Ten separate final-source
processes passed, exit 0 each.

The three original admission oracle bodies are restored: 503, no Batch and no
POST, including the unevaluable policy error. Their synthetic local policy
fixtures are explicitly injected into the new G0 seam; remote Platform callbacks
remain G1 and may discover a new shared failure after acceptance. A separate
adapter reruns the untouched historical test bodies from the prior hash-verified
snapshot with only this fixture wiring migrated: **3 passed, exit 0**. The raw old
fixture's mixed callback is not claimed to prove a split. New tests additionally
prove ISSUED token, unchanged Batch journal, ACCEPTANCE_PENDING reconciliation,
repair/retry once, duplicate refusal and rejected malformed shared verdicts.

The fake "platform_unreadable" Asset response now raises the production
Bootstrap remote-validation error rather than an origin-free RuntimeError.
The unchanged busy/recovery/TimeoutError/ConnectionError local tests still pass;
an origin-free RuntimeError has its own global/no-peer-POST negative test.
The existing Cloudflare test's expected Python exception changes to the new
source-typed configuration error; its socket fixture is NOT_RUN here.

## Observed final-source validation

Python 3.12.13, repository root, `/tmp/plasma-ppu-trust-gate1a-venv/bin/python`.
All logs/command manifests below live in `.plasma-path3-evidence/` and are
collected by the trusted workflow, excluded from source publication.

| Check | Observed result |
| --- | --- |
| Unchanged probe, `WP01_REQUIRE_CONTRACT=1` | **5 passed**, exit 0. Probe SHA unchanged. |
| Original selected regression suite | **307 passed**, exit 0. Includes original API/admission, single-Site Flash, rollback/restart, Retry/SAFE_OFF/Stop and identity tests. |
| Existing focused lane module | **29 passed × 3 final-source processes**, each exit 0. |
| New shared-authority/lane module | **48 passed × 3 final-source processes**, each exit 0, plus the standalone final suite invocation. |
| Repaired journal test | **1 passed × 10 final-source processes**, each exit 0. |
| Historical unchanged assertion bodies, explicit G0 fixture adapter | **3 passed**, exit 0. |
| Serial lane scheduler negative control | Expected **exit 1**, one failure / 28 deselected: `healthy POST must precede slow lane release`. A test-process plugin sets the lane pool to one worker; no source mutation or signature mismatch. This simulates serial dispatch, not a claim to execute a full historical checkout. |
| Broad six modules + all `test_manager*.py` + new authority module | Raw **415 passed, 29 failed, 51 errors**, exit 1. Every one of the 80 failure/error summary rows reports OS socket permission denial. Those integration cases are **NOT_RUN**, not passing and not independently established functional failures. |
| Relevant socket suites | Raw **11 passed, 9 failed, 2 errors**, exit 1. All 11 failure/error rows are TCP/Unix socket permission denials; affected behaviors **NOT_RUN**. No sandbox/permission workaround. |
| `git diff --check` | exit 0. |

Event tests cover 1/2/8 Sites per healthy PPU while another PPU is held in
Platform/readiness/Plan/Start, all healthy POST events before release; same-PPU
independent Site holds cover 2/8 Sites. A single-lane case exercises the same
G0/G2 path. Existing held-HTTP tests also hold real fake-Gateway calls in
readiness/Plan/synchronous Start for cross-PPU and same-PPU cases. A one-Site
PPU cannot have an unrelated second Site; no impossible same-Site parallelism
is asserted. Late failures at reservation, Start and pre-POST preserve an
already accepted peer Job and consumed/reconcilable Batch, stop unsent peers
without fabricated outcome, reject later admission and never resend.
These are host-only fakes, not physical concurrency or electrical evidence.

Exact primary commands:

```sh
WP01_REQUIRE_CONTRACT=1 PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q specs/engineering-dispatch/evidence/wp01_shared_gate_probe.py
```

Observed exit 0; log `probe.test.log`.

```sh
PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q software/python/tests/test_programming_shared_authority.py
```

Observed exit 0; log `authority.test.log`.

```sh
PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q software/python/tests/test_programming_batch_lanes.py software/python/tests/test_programming_batch_coordinator.py software/python/tests/test_programming_batch_targets.py software/python/tests/test_bundle_programming_workflow.py software/python/tests/test_programming_start_reconciliation.py software/python/tests/test_programming_start_journal_rollback.py software/python/tests/test_manager_server_persistence_wiring.py software/python/tests/test_manager_persistence_schema.py software/python/tests/test_manager_config_compat.py software/python/tests/test_manager_transport_state.py software/python/tests/test_manager_ps_only_topology.py
```

Observed exit 0; log `selected.test.log`.

```sh
PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q software/python/tests/test_ppu_execution_ownership.py software/python/tests/test_runtime_activation.py software/python/tests/test_manager_readonly_contract.py
```

Observed exit 1; log `sockets.test.log`.

Broad command: `.plasma-path3-evidence/broad-command.json` lists every argument,
`broad-exit.txt` records 1, and `wp01_broad_final.py` reproduces enumeration.
Repeat commands/exits/summaries: `repeats.json`, `wp01_repeat_checks.py` and
`journal-{1..10}.test.log`, `lanes-{1..3}.test.log`,
`authority-repeat-{1..3}.test.log`. Original/negative commands and exits:
`controls.json`, `historical-split.test.log`, `serial-negative.test.log`, plus
copied `/tmp` adapter/plugin sources. All pytest commands set
`PYTHONPATH=software/python`; the negative adds `/tmp` for its plugin.

## Exact tested source SHA256

HEAD intentionally remains pinned while the trusted publisher owns commit/push.
These hashes identify the tested working-tree production/test files, not a
fictitious published commit. No code edits occurred after this manifest.

```text
1065d51818fecbdd669ba76203ee51fa2a70a3dc67dd215448cb2c35258c83f6  software/python/plasma_manager/bootstrap.py
ae142271b232cc3d92a06346a57dd34d15d9b62cbfc042d5c8b25852ee70b987  software/python/plasma_manager/bootstrap_server.py
9033c9fda8dd0775a0f63b470a8d8c14f43e8f8aa080792c0f87d3d755d7838d  software/python/plasma_manager/client.py
568441631d73594d0dfbe09d5ca35680212163fb9a4c53af6bf3bdd34ad37255  software/python/plasma_manager/poller.py
f56fd8ab8492937ec8c06b23859679dec20cb90d1c1881eaba08ed791638bac3  software/python/plasma_manager/programming.py
a6e80e27c1540c2904d6697c76db469d530c568d604581e37ba7febebed166c8  software/python/plasma_manager/programming_batch.py
0fd71a2b5f2a35102f0cac86236312b31d9798cca4a1dd3aca156847a80cc919  software/python/tests/test_manager_cloudflare_access_transport.py
e5880fa3b7318b3bde6fc5ebc94be429333d95ab73dccaf7ba29e3c131d56e7b  software/python/tests/test_programming_batch_targets.py
6e7b5baebd3fe70696aaf02e429bf0aff6198ed0b636db85232d2a06f2731068  software/python/plasma_manager/shared_control.py
871d94c476827ed85f550e8faa23517586b16e24565cff0c87d94f0d7a46e064  software/python/tests/test_programming_shared_authority.py
05480d409d2d2f9b4b44042e88862b5399eab2e376b182b206523c12e61fcbf1  specs/engineering-dispatch/evidence/wp01_shared_gate_probe.py
```

Prior public baseline snapshots, rechecked for the historical adapter:

```text
bc270fae0aa35997b41b7bde60da3586a44f79ae33fa7632c7337df213e27794  /tmp/wp01-baseline-programming_batch.py
17c34290733756f4d2d6a5db395608ab4a22103caf4e74dcd640311fcb078173  /tmp/wp01-baseline-test_programming_batch_targets.py
```

## Publication, CI and remaining acceptance

The reviewed workflow `.github/workflows/plasma-engineering-runtime-dispatch.yml`
requires candidate HEAD to remain **uncommitted at the pinned source**, then its
trusted publisher rechecks the live PR/source, commits and non-force-pushes to
the same PR ref **after this agent exits**. This step has prepared production,
tests and this report for that handoff. No direct push/API write was attempted.

Exact published HEAD: **PENDING / NOT_VERIFIED**. Actual final-HEAD CI:
**NOT_VERIFIED**. The read-only `gh api repos/physicslu/plasma/pulls/1441` attempt
exited 4 because GH_TOKEN is intentionally unavailable in the model step;
credentials were not sought elsewhere. The executing run/job above is known;
its terminal result cannot be observed while inside it. No current PR state,
check-runs, rulesets/reviews/threads/mergeability or future publisher success
is asserted from old evidence.

Remaining: socket/API integration in a capable authorized executor, trusted
publication and exact-final-HEAD hosted CI, independent review and PR #1439
stack dependency before Gate 2 readiness. Gate 2 remains owner-only; no merge
or auto-merge. Hardware, Z2/DUT/FPGA, SWPC services, USB/SSH/sudo, deployment and
real Flash: **NOT_RUN**. No physical SAFE_OFF or recovery qualification claim.
No model-request/token/billing metrics are available in this step; no inferred
subscription use. Inspection ended after required code/test evidence and
source hash verification; pending integration is reported without another Gate.


## Independent post-publication checkpoint (2026-11-15)

The trusted Path 3 run [43697191800](https://github.com/physicslu/plasma/actions/runs/43697191800) completed: `development-authorize` SUCCESS, `development-codex` SUCCESS; its candidate source and this evidence were published at exact PR #1441 HEAD `24a0fa939845aa35e6676ed2333821fc0f13cacb`. This is a **post-publication verification**, not a change to the preceding original-executor evidence or its claims.

At that HEAD, 14 pull-request-triggered GitHub Actions runs were observed as `completed/action_required` with **zero executed successful jobs**. They are not functional test failures or CI PASS. This checkpoint only updates the existing evidence record on the same Draft PR to request a fresh CI trigger from a non-automated source edit; **actual subsequent workflow execution and conclusions must be verified against the resulting new commit**. The pending socket-bound integrations remain NOT_RUN and cannot be re-labelled by this edit.

Independent source-delta audit relative to main `98652acaba5b1bb5f3e32bb6aa1d6a21219e5d6a` at the published source: production files **527 insertions / 154 deletions** (net +373) across 7 files; tests and evidence are tracked separately. Source priority for final acceptance: retain G0 refusal/unconsumed start ID, local G1 isolation, G2 pre-submit fail-closed, journal/UNKNOWN evidence and real one-Site Flash safety. Do not shorten these guards just to reduce LOC. #1439 remains a separate, unmerged documentation dependency. No merge, deployment, Z2/DUT or physical HIL was authorized.
