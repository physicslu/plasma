# PR #1214: generic package API/Coordinator host-only bridge

Observed on 2026-10-30, Path 3, Runner `SWPC-plasma-codex`, run `40975883341`, job `development-codex`. Base source: `e9d63be7b169b6af8e7e97dd7b3cbd643323a657` (detached HEAD, initially clean). Canonically serialized authenticated event Work Order SHA256 matched `714e2905f3b588431009d46c461c2ab6db1e2499470090dda92e977263d9fcbf` and its source SHA matched HEAD.

## Implemented scope

- Existing Bootstrap service accepts a **Python test-injected composition only**, with a temporary state root and independently injected runner/admission policy. No CLI, environment or public request can select that composition. Default runtime runner cannot be combined with package admission. Normal live API/client denial remains intact.
- Test admission binds a fixture-approved publisher, source commit, archive digest and target profile independently of manifest/request claims. API preflight checks committed bytes, generic ZIP validation and requested kind before queueing. The existing Coordinator repeats package verification under its existing lock; publisher/source/digest and generated API ID are recorded in its existing journal. Success requires exact runner/journal identity, terminal package state and provenance correlation.
- Existing Coordinator receives an optional test scheduler exclusion context. Tests model blocking admissions before the final eight-Site/job/hardware/authority check, keeping the fence through staging/verify/rollback, and retaining it on uncertain recovery. **This fixture is not an implemented production scheduler interlock.**
- Cached active release corruption now requires recovery, rather than reporting rollback to damaged bytes.
- Shared inert package fixtures support existing pytest tests and the new dependency-free unittest suite. Existing cached-release regression expectation changes to recovery_required.

## Observed validation

Command (exit 0):

```sh
/opt/plasma-ci/bin/python3.11 -m unittest discover -s software/python/tests -p test_ppu_package_api_bridge_gate1.py -v
```

Observed: `Ran 13 tests ... OK (skipped=3)`; full output in `unittest.log`. Parameterized subcases cover native C, Python, FPGA and initial engineering module examples; trusted grant mismatch, manifest/source/target mismatch, cross-kind/traversal/missing FPGA pair, API ID mismatch, existing Coordinator lock conflict, eight-Site/job/hardware/authority denial, concurrent programming denial, stage/activation rollback and unknown recovery, repeated submissions and cached corruption. The actual SWPC API client upload method drives actual Bootstrap HTTP handlers over in-memory byte streams, then the real queue/worker and Coordinator sandbox, followed by client status reconciliation. Package submission uses the client's internal request primitive strictly in this fixture; public submit still rejects before transport. No real HTTPS request, payload execution or FPGA load occurs.

Three real loopback HTTP subcases are **NOT_RUN/skipped**: sandbox socket creation raises `PermissionError: [Errno 1] Operation not permitted`. In-process tests patch only the socket server constructor, not upload, request handling, worker, Coordinator, lock, journal or verifier logic.

The compile check exited 0. The initial `git diff --check` exited 0 only because
the new fixture was still untracked; the trusted publish step later staged it
and failed on a blank line at EOF. It did not publish a commit.

```sh
/opt/plasma-ci/bin/python3.11 -m compileall -q scripts/ppu-bootstrap-service.py scripts/ppu-bootstrap-deployment.py software/python/tests/ppu_package_fixtures.py software/python/tests/test_ppu_generic_package_host_only_gate1.py software/python/tests/test_ppu_package_api_bridge_gate1.py
```

Existing focused pytest command could not run (exit 1):

```sh
/opt/plasma-ci/bin/python3.11 -m pytest -q software/python/tests/test_ppu_package_api_bridge_gate1.py software/python/tests/test_ppu_generic_package_host_only_gate1.py software/python/tests/test_ppu_single_deployment_entry_gate1.py
```

Reason: `No module named pytest`. Attempted isolated setup:

```sh
/opt/plasma-ci/bin/python3.11 -m venv /tmp/plasma-1214-tests
/tmp/plasma-1214-tests/bin/python -m pip install pytest PyYAML pytest-asyncio
```

Installation failed (exit 1): package-index DNS unavailable. No worker/system installation was performed. Broader pytest/CI remain **NOT_RUN**, not PASS.

## Delivery and remaining blockers

Source changes: `scripts/ppu-bootstrap-service.py`, `scripts/ppu-bootstrap-deployment.py`, `software/python/tests/test_ppu_generic_package_host_only_gate1.py`; new `software/python/tests/ppu_package_fixtures.py`, `software/python/tests/test_ppu_package_api_bridge_gate1.py`, and this evidence directory.

Git fetch failed: `.git/FETCH_HEAD` is read-only. Branch/commit/push and PR mutation were not attempted after confirming this restriction. Deliverable is the working-tree diff, including new files; no new commit. PR #1214 has not been marked Ready or merged; live remote Draft/HEAD/CI could not be independently revalidated here.

Production package installation remains unqualified: deployed TLS and authenticated/revocable Master/publisher authorization, independently trusted target installation authority, actual programming admission ownership/quiescence, immutable on-target staging/activation/rollback, reboot/unknown-outcome recovery, protected FPGA Image/Manifest/HWH/ABI admission and cross-host compensation require further work and separately authorized acceptance. Publisher fixture binding is not signature verification or live publisher authentication. FPGA test data is inert and does not qualify the protected image Manifest. The temporary sandbox stages files/receipts only and never runs C/Python. Root Guard, Golden Recovery, runtime kit path and legacy deployment routes are unchanged.

SWPC/PPU/Z2 deployment, FPGA programming, DUT activity and physical qualification: **NOT_RUN by scope**. No Gate 2 request; keep Draft and complete remaining Gate 1 validation/publication before readiness review.

## Artifact recovery and independent Host-only validation

The first Run's Artifact ID `12943260749` (`plasma-development-codex-40975883341`)
was downloaded and restored against the exact Draft PR HEAD
`e9d63be7b169b6af8e7e97dd7b3cbd643323a657` in an isolated local clone.
Its Receipt names that SHA, Run `40975883341`, the SWPC Path 3 Runner and
`EVIDENCE_READY_REVIEW_REQUIRED`. SHA256 of the Receipt, Source Patch and
engineering evidence tar matched the uploaded sidecars. The new-file tar
contained the expected fixture, API bridge test and report; Codex private logs
were not restored into source. Run `40984795797` supplied failure diagnostics
only and published no source changes.

Recovery removed the fixture's EOF blank lines. Pytest collection was fixed
with package-relative fixture imports. Three focused regressions were
corrected: a damaged active cached release now expects `recovery_required`,
and two legacy-installer denial tests use an isolated product root instead of
assuming the host's `/opt/plasma` does not exist. No production installer or
hardware path was enabled by these changes.

Independent commands and observed results in an isolated Python 3.11 venv:

- `python -m pytest -q` across API bridge, generic package, single entry,
  Bootstrap deployment/network/core: **135 passed, 3 skipped, 26 subtests
  passed** (exit 0). The three skipped cases require loopback sockets that
  this sandbox denies; in-memory HTTP handler tests passed.
- `python -m pytest -q` across SWPC API client, unified engineering
  transaction, Z2 Bootstrap call graph and Bootstrap composition:
  **65 passed** (exit 0).
- `/opt/plasma-ci/bin/python3.11 -m unittest discover -s software/python/tests
  -p test_ppu_package_api_bridge_gate1.py -v`: **13 methods OK, 3 subcases
  skipped** (exit 0), before the package-relative import adjustment.
- Python 3.11 `compileall` for changed source/tests and `git diff --check`
  with all new files represented in the index: **PASS** (exit 0).

This recovery has not produced an authenticated PR commit or new CI run.
The trusted Path 3 publisher requires a live same-HEAD candidate checkout;
the prior worker could not download the Artifact because of DNS and had no
GitHub token in the Codex namespace. Until a supported trusted handoff
publishes these validated bytes, PR HEAD remains the pinned source and
Gate 2 readiness is **NOT_MET**. Production install and physical acceptance
remain **NOT_RUN/NOT_QUALIFIED** as described above.

## Deployment Channel Completion Gate 1 follow-up (2026-10-30)

This follow-up starts from exact Draft PR #1214 HEAD
`e0516ff0371018d2079883d9924903a3ffec61ba` and main
`a22c9cb04a9ea1361a39d2504fc83f510898390e`. Earlier publication-status
statements above describe the prior recovery checkpoint, not this follow-up.

The public `BootstrapAPIClient.submit()` now sends `python`, `native-c`, and
`fpga-image` package requests with only `kind` and `upload_id`. It rejects
caller-supplied runtime identity fields for those kinds; the server remains the
authority. The in-memory API integration now uses public `upload()`, `submit()`,
and `deployment_state()` rather than private `_call()` for generic submission.
The real-loopback test also uses those public methods. A missing loopback socket
is now a test failure, not a silent skip; Python CI has a focused verbose step
that reports the three subcases separately.

Observed in an isolated Python 3.11 environment, with only local `127.0.0.1`
socket permission for the loopback test: seven related test modules **170 passed,
29 subtests passed** (exit 0); focused loopback **1 test, 3 subtests passed,
0 skipped** (exit 0). This is Host-only HTTP, not HTTPS/TLS or a live PPU.
GitHub-hosted results for this follow-up remain pending until publication and
CI execution; the earlier successful aggregate CI cannot qualify these new
bytes.

The formal deployment channel is still **BLOCKED**, for concrete missing
dependencies:

- The installed Bootstrap service still runs commissioning HTTP with a
  device-local Bearer token, and its ordinary server constructor has no
  independently authenticated Master/publisher policy, generation/revocation,
  source approval, or TLS listener. The generic admission callback is only
  accepted with a temporary test state root and injected runner. Live generic
  submission is rejected before activation.
- `SiteManager.enqueue()` uses process-local admission/owner state. The
  Bootstrap Coordinator is a separate process and its optional test exclusion
  defaults to `nullcontext()`. No shared production fence can atomically block
  new jobs, prove eight-Site idle, or establish real hardware quiescence.
- The existing on-device installer is PS Runtime-only. Generic ZIP activation
  in the Coordinator is restricted to a temporary sandbox; no independently
  trusted target installer/activation or two-host recovery exists. FPGA fixture
  bytes do not qualify Image/Manifest/HWH/ABI or protected Root/Golden recovery.
- PR #1215 is a Draft architecture dependency. It and #1214 both edit
  `docs/README.md`; the documentation decision and integration order require
  reconciliation before a production client-neutral claim.

No formal generic server admission, product install, TLS bypass, scheduler
interlock claim, deployment, service restart, SWPC/Z2/FPGA/DUT operation, or
Gate 2 qualification is created by this follow-up. The smallest remaining
implementation is an installed PPU TLS/authentication trust boundary, a
shared scheduler/Coordinator exclusion with real quiescence evidence, and
bounded generic activation through the existing Coordinator and installer
functions. These must be implemented and tested before enabling live generic
requests. Keep PR #1214 Draft.

### Published follow-up and per-kind CI evidence

The first follow-up commit is
`d3e2d3e32dd327d5fb553f6b41d947dd15eacbc9`. GitHub-hosted Python Run
`41004427207`, Job `123895976814`, completed the full Python/PL suite with
**2839 passed, 12 skipped, 5679 subtests passed**. Its focused loopback step
reported **1 method and 3 subtests passed, 0 skipped**. That result proves all
three loopback subcases executed, but the Job log did not name each passing
subcase separately. The 12 skips belong to the larger suite and are not
counted as loopback PASS evidence.

The following incremental correction makes Python, native C, and FPGA each a
separately named test method. In the isolated Python 3.11 environment, the
focused command reported **three named PASS, zero SKIP**; seven related modules
reported **172 passed, 26 subtests passed**. GitHub-hosted evidence for this
incremental correction must be checked on its own eventual commit. No formal
server authorization, scheduler fence, generic product installation, or
hardware qualification is inferred from these tests.

### Exact-code-commit CI and Gate 2 readiness matrix

The per-kind correction was published as code commit
`7a6e1482408751805189d819e6c197aff72cc5db` (parent
`d3e2d3e32dd327d5fb553f6b41d947dd15eacbc9`, non-force expected-SHA
update). On this exact code commit, GitHub-hosted Python Run
[`41004918189`](https://github.com/physicslu/plasma/actions/runs/41004918189/job/123897527658)
reported **2841 passed, 12 skipped, 5676 subtests passed** in the full suite.
Its focused step separately reported:

| Loopback method | GitHub-hosted Linux result |
| --- | --- |
| `test_authenticated_http_python` | **PASS** |
| `test_authenticated_http_native_c` | **PASS** |
| `test_authenticated_http_fpga_image` | **PASS** |

The focused step reported **3 passed, 12 deselected, 0 skipped**. The full
suite's 12 skipped tests are separate; they are not counted as passing.
Repository contracts documentation, route, and terminology jobs in Run
[`41004917985`](https://github.com/physicslu/plasma/actions/runs/41004917985)
all passed. Bootstrap script, QEMU simulation, Z2 runtime-kit build, and other
applicable checks on this code commit passed; QEMU and build results do not
prove physical Z2 execution.

| Gate 2 item | Status | Evidence / remaining dependency |
| --- | --- | --- |
| Public generic API client and three loopback kinds | **PASS (Host-only)** | `scripts/ppu_deploy_api.py` public `submit()` and `software/python/tests/test_ppu_package_api_bridge_gate1.py`; Python Run `41004918189`. |
| API/Coordinator Lock, Journal, receipt and simulated Rollback | **PASS (Host-only)** | Existing bridge and generic package regression tests in Python Run `41004918189`; no product install claim. |
| Live TLS, authenticated Master/publisher/source/replay policy | **BLOCKED** | `scripts/ppu-bootstrap-service.py` still uses commissioning Bearer/HTTP; generic admission remains test-only. |
| Atomic production eight-Site Job fence and hardware quiescence | **BLOCKED** | `software/python/plasma_server/site_manager.py` and `scripts/ppu-bootstrap-deployment.py` have no shared production exclusion or hardware quiescence proof. |
| Generic on-device activation and cross-host recovery | **BLOCKED** | Current installed installer is PS Runtime-only; generic Coordinator staging is temporary Host-only sandbox. |
| FPGA Image/Manifest/HWH/ABI, Root Guard and Golden recovery integration | **NOT_VERIFIED** | Root guard remains separate; inert FPGA fixture and QEMU do not qualify it. |
| PR #1215 dual-client architecture/document index reconciliation | **BLOCKED** | #1215 is still Draft and also edits `docs/README.md`; no production client cutover claim. |

**Host-only Gate 2 readiness: NOT MET.** The minimum remaining dependencies
are trusted on-device TLS/authentication with revocation and publisher/source
admission; a real shared scheduler/Coordinator fence with eight-Site and
hardware quiescence authority; and bounded generic activation/recovery through
the existing on-device deployment components. Keep the live generic path
fail-closed until these are implemented and independently tested. No service
activation, deployment, hardware action, or merge occurred in this Gate 1.
