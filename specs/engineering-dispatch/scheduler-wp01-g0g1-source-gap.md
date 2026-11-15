# WP-01 option 3 source audit — GAP; implementation NOT_ACCEPTED

2026-11-15. Input/tested HEAD **`b074bd3bafc5c06eaaf7aea3e505464cd98360d8`**.
Path 3, `workspace-write`, Runner `SWPC-plasma-codex`, executor `development-codex`,
[run 43682903363 / job 132717222506](https://github.com/physicslu/plasma/actions/runs/43682903363/job/132717222506).
Owner [Work Order](https://github.com/physicslu/plasma/issues/981#issuecomment-6889984278)
SHA256 `17446f00356efa7dc80bcf921ec098f3283457a857915d387f62e2ca35af6e62`
was recomputed from the event JSON with sorted keys, compact separators and
`ensure_ascii=False`; MATCH. Event owner: `physicslu`; PR 1441 and source SHA match.
Root AGENTS, Common, Path 3, Manager, unified architecture §5.3/§5.7, previous
admission Gap and the exact owner-approved option 3 decision were read.

**Disposition: source-backed G0/G1 separation has not been established. Publish
this evidence and diagnostic probe only, under the Work Order's explicit
unproven-split stop condition. No runtime or historical test expectations changed.**
Option 3 is already approved; this report does not request another approval or
claim that option 3 is intrinsically impossible. The previous unresolved-callback
causality argument does not by itself disprove a correctly decomposed authority.
The concrete unresolved issue here is failure-origin classification inside the
production dependencies, beyond the three non-null checks.

## Source audit and reproduced counterexamples

The proposed seam is `bootstrap_server.py:platform_gate_reason`. It checks class
`registry_store`, `poller`, `bootstrap_coordinator` for non-null, then calls
`_platform_mutation_block` and converts **every** exception to
`TARGET_STATE_UNAVAILABLE`. That invocation is not exclusively a remote read:

| Call path | Actual state read / unresolved authority |
| --- | --- |
| `_platform_mutation_block` → `_alias_has_active_execution` → `_fleet_item_for_alias` → `FleetPoller.snapshot` | Local cached fleet state. `server.py` catches `RuntimeError` as no item. `FleetPoller` has no separate shared-health admission method; `snapshot` reports cache metadata, not thread liveness. A stopped poller with a cache is still non-null. |
| `_platform_mutation_block` → `_bootstrap().status` → `ManagerBootstrapCoordinator._live` → `_entry` | Shared registry lookup precedes remote I/O. Arbitrary registry/control failures are inside the broad local conversion. |
| `status` → `_live` → `BootstrapHttpClient.__init__` → `PPUHttpClient.__init__` → `_cloudflare_access_headers` | Manager-wide transport/service-identity configuration is read **before any network call**. `client.py` explicitly distinguishes this deployment state from PPU registry state, but uses `PPUTransportError` for missing global identity as well as remote transport failure. |
| `status` → `credentials.public_state` / `_authenticated` → `credentials.record_for` | Shared in-memory credential store/policy and per-alias enrollment are interleaved with anonymous/authenticated remote status. An arbitrary shared-store exception is converted to local state unreadability. |
| `BundleProgrammingWorkflow.target_block` → `coordinator.assets` → `_authenticated` | Same shared registry/credential/config dependencies; `target_block` catches all remaining exceptions as local. Splitting only the Platform callback leaves this second downgrade path. |
| `FleetPoller.refresh` → `FleetObservationStore.fleet_snapshot` → `FleetAggregator.fleet_snapshot` | Registry enumeration, per-PPU polling and shared observation/schema/persistence machinery are mixed. `_last_refresh_error` records an untyped exception; a new G0 cannot infer failure domain solely from that string or from a non-null poller. |
| Batch `_dispatch_block` and workflow `_submit_job` | Existing latches protect dispatch and journal-before-POST. There is no injected live shared-authority check at these boundaries. A pre-admission-only callback would not establish G2 revalidation, especially with held Start/pre-submit work. |

The committed [diagnostic probe](evidence/wp01_shared_gate_probe.py) exercises
production Handler, Bootstrap coordinator, credential store and transport client
construction using synthetic local fixtures. The two service-identity cases
assert **zero network calls**. It does not read actual credentials or access a PPU.
Its default assertions describe the pinned defects; its passing exit is evidence
of reproduction, **not acceptance**. `WP01_REQUIRE_CONTRACT=1` activates the
required safety oracles and fails on the same source.

| Probe | Observed pinned behavior | Required / missing proof |
| --- | --- | --- |
| Incomplete shared CF Access service identity, Platform read | `TARGET_STATE_UNAVAILABLE / PPU_PLATFORM_STATE_UNREADABLE_PPUTransportError`, zero network | Shared Manager configuration must not be silently local. |
| Same global identity failure, Site read | `TARGET_STATE_UNAVAILABLE / PPU_STATE_UNREADABLE_PPUTransportError`, zero network | Platform-only decomposition does not fix Site classification. |
| Ambiguous `RuntimeError` from shared `credentials.public_state` | `TARGET_STATE_UNAVAILABLE / PPU_PLATFORM_STATE_UNREADABLE_RuntimeError` | Unknown-origin shared judgement must fail closed. |
| Stopped real `FleetPoller`, synthetic `runtime_absent` Bootstrap status | Platform verdict `None` | Non-null check does not prove poller health. The fail-closed probe tests the proposed health requirement; this is not a claim that existing source defines stopped-poller refusal. |
| Real Handler with missing registry/poller/coordinator | HTTP **202**, Start **CONSUMED**, Batch journal changed, reconciliation **TERMINAL_CONFIRMED**, zero POST | Initial G0 must instead preserve 503, unconsumed ISSUED Start, unchanged Batch journal, admissible/read-only reconciliation. |

Moving the non-null test into G0 would fix only the last row. Treating
`PPUTransportError` or every `_bootstrap().status` exception as remote would keep
the first three unsafe classifications. Treating every Bootstrap exception as
global would instead turn a real local PPU timeout into a whole-Batch failure.
No new authority, cached blanket approval, async-admission fallback or revised
wire semantics was introduced to make those cases green.

The remaining engineering proof requires source-scoped separation of local
Manager policy/store reads from actual remote reads, explicit propagation of
unclassified failures through **both** Platform and Site gates, independently
falsifiable shared-control health, and the same shared authority at durable
admission and submission transitions. It must establish that a remote fault
cannot silently inherit authority to refuse initial admission. These are
unresolved implementation/proof tasks under the approved direction, not a new
owner permission gate or a blanket prohibition on host-only development.

## Executed checks and exact logs

All test commands used repository-root `PYTHONPATH=software/python` and
`/tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q` (Python 3.12.13).
Logs below are under `.plasma-path3-evidence/`, packaged by the trusted workflow.
The probe is deliberately outside automatic `tests/` discovery.

| Arguments / environment | Actual exit/result | Log basename |
| --- | --- | --- |
| `-s specs/engineering-dispatch/evidence/wp01_shared_gate_probe.py` | 0; 5 reproduced defects in 0.34s | `wp01-g0g1-probe.test.log` |
| `WP01_REQUIRE_CONTRACT=1`, same probe without `-s` | 1; 5 failed safety/admission oracles in 0.12s | `wp01-g0g1-oracles.test.log` |
| `software/python/tests/test_programming_batch_lanes.py` | 0; **29 passed** in 1.99s | `wp01-g0g1-focused.test.log` |
| Broad command below | 1; **367 passed, 29 failed, 51 setup errors** in 50.52s | `wp01-g0g1-broad.test.log` |
| Selected command below | 1; **306 passed, 1 failed** in 8.81s | `wp01-g0g1-selected.test.log` |
| Socket command below | 1; **11 passed, 9 failed, 2 setup errors** in 1.08s | `wp01-g0g1-sockets.test.log` |
| `WP01_BASELINE=1`, `/tmp/test_wp01_historical.py` | 0; **3 passed** in 0.19s | `wp01-g0g1-historical-baseline.test.log` |
| Same original oracles against pinned coordinator | 1; **3 failed**, DID NOT RAISE ProgrammingError, 0.28s | `wp01-g0g1-historical-pinned.test.log` |
| Journal case below, five separate processes | exits **0, 0, 0, 1, 1**; 3 pass / 2 fail | `wp01-g0g1-journal-repeats.test.log` |

Broad command:

```sh
PYTHONPATH=software/python /tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q \
  software/python/tests/test_programming_batch_lanes.py \
  software/python/tests/test_programming_batch_coordinator.py \
  software/python/tests/test_programming_batch_targets.py \
  software/python/tests/test_bundle_programming_workflow.py \
  software/python/tests/test_programming_start_reconciliation.py \
  software/python/tests/test_programming_start_journal_rollback.py \
  software/python/tests/test_manager*.py
```

Selected command uses the same six explicit modules, followed by these five
instead of the glob: `test_manager_server_persistence_wiring.py`,
`test_manager_persistence_schema.py`, `test_manager_config_compat.py`,
`test_manager_transport_state.py`, `test_manager_ps_only_topology.py`, all under
`software/python/tests/`. The one failure was
`test_programming_batch_targets.py::test_a_journal_that_cannot_be_written_stops_submission_and_says_so`:
line 848 expected an unsubmitted peer outcome `None`, observed `BLOCKED`.
The unchanged case passed in the broad run; five isolated executions reproduced
both results. **Unresolved nondeterminism; no green 307/307 claim.** No oracle
was weakened and no runtime fix is claimed. All reported occurrences still
asserted zero peer POST; this does not prove the classification race harmless.

Socket command uses `test_ppu_execution_ownership.py`, `test_runtime_activation.py`,
`test_manager_readonly_contract.py`, all under `software/python/tests/`.
All 80 broad failure/error summary rows report `PermissionError: Operation not
permitted`. Socket-suite failures are TCP bind and Unix-socket creation denials.
Those affected integration behaviors are **NOT_RUN**, not functional PASS.
No privilege/sandbox workaround was attempted.

The 29 current lane cases include held readiness/Plan/Start across PPUs and
independent same-PPU Sites, 2/8-Site overlap, late shared latch with accepted Job
observation, Stop, PPU UNKNOWN/no resend, journal boundaries, exact owner/resource/
image, same-Site exclusion and SAFE_OFF/Retry. Selected tests also cover one-Site
and legacy Flash workflow. These prove existing host-only behavior; **new G0
acceptance and its complete 1/2/8-lane matrix are NOT_IMPLEMENTED / NOT_RUN**.
The old serial-scheduler negative control was not rerun; prior evidence remains
in `scheduler-wp01-presubmit-evidence.md`, not claimed as this run's result.

Historical snapshots/wrapper were reused only after their SHA256 values matched
the previous Gap report. Original test bodies were not changed; the baseline
module shares current workflow/fake fixtures, so this isolates coordinator
semantics rather than validating a complete historical checkout.

```text
bc270fae0aa35997b41b7bde60da3586a44f79ae33fa7632c7337df213e27794  /tmp/wp01-baseline-programming_batch.py
17c34290733756f4d2d6a5db395608ab4a22103caf4e74dcd640311fcb078173  /tmp/wp01-baseline-test_programming_batch_targets.py
eb2b0ea785247802297efa2b3d2c34619d942cd3723f2e4214b64b9ffbcb8d57  /tmp/test_wp01_historical.py
05480d409d2d2f9b4b44042e88862b5399eab2e376b182b206523c12e61fcbf1  specs/engineering-dispatch/evidence/wp01_shared_gate_probe.py
d274bc134bbcf4ba2577fac9b81c4761c209c94424e34d730a93d12899d934e8  software/python/plasma_manager/bootstrap_server.py
602997e513337949dc8480a54ddac718e73037ba0222ad0f520ca6da942e9105  software/python/plasma_manager/bootstrap.py
22e6d418ba185eda64cbac8094a1433d56f1ab58e2b20f19cc5429cffcefcf08  software/python/plasma_manager/programming.py
38d888ccde4a797d36301a9222d1a3b7829b056c072d063b63c922899da1feba  software/python/plasma_manager/programming_batch.py
e1add7060f4730e9076633ba43dfbcc926f22173ad85e6c52ef56dceffd471d5  software/python/plasma_manager/poller.py
df316d5fce9d92fa7a297a0c66f2f70bae1555d84f1d99cfb3f95e2e123087cf  software/python/plasma_manager/client.py
```

## Publication, CI and remaining blockers

A read-only GitHub observation verified PR #1441 **open, Draft, unmerged**, exact
input HEAD above. Its 13 input-SHA hosted runs showed 12 completed/success and
Python PS source tests `43682880102` still in progress. The commit status endpoint
returned no legacy statuses; that is not proof that check-runs passed. No final-HEAD
CI PASS is claimed. Current engineering job and trusted publication were pending.

Only this report and the diagnostic probe are publication changes. Candidate
HEAD must stay **uncommitted** at the pinned SHA: the reviewed workflow's trusted
publisher commits/pushes after this agent exits and rechecks the live PR HEAD.
No alternate push/API write route is used. Final published SHA and its hosted CI
are **PENDING / NOT_VERIFIED**, inherently unavailable during this agent step.
The workflow packages `.plasma-path3-evidence/`; raw Codex logs are not source
publication files. The receipt report is `.plasma-path3-evidence/engineering-report.md`.

Remaining blockers: correct source-verified split and acceptance, reproduced
journal-classification nondeterminism, socket integration in a capable executor,
trusted publication/final-HEAD CI, independent review and #1439 dependency before
Gate 2 readiness. PR remains Draft; no Gate 2 approval/merge or deployment.
SWPC service changes, SSH, Z2, FPGA, DUT, USB/TTY, privilege changes and real Flash:
**NOT_RUN**. No physical SAFE_OFF or electrical/recovery qualification claim.
Token/model-request/billing metrics are not available here; no subscription
consumption is inferred. Inspection stopped after required Gap evidence and
bounded verification; no production edits were made to hide a failure.
