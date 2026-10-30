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
