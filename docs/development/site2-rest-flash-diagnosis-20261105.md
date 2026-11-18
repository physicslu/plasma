# Site 2 REST Flash diagnosis — 2026-11-05

Status: **BLOCKED for real failure diagnosis and Gate 2 readiness**. Host-only
snapshot omission repaired; no runtime or hardware repair claimed.

- Path: Path 3, default `workspace-write`, executor `SWPC-plasma-codex`.
- Current Actions Run: `41926147476`, job name `development-codex`.
- PR: #1304; pinned candidate HEAD: `2256309e83f6a6a46de5cf68b3b2e4a09b3b472a`.
- Trusted main checkout: `7fd1d39f63a42d3accfbc3dff33cbf37219d68ad`.
- Owner event Work Order canonical SHA256 verified:
  `4a4f889650742a15f9d22d0a1d70a5dc1c0dec2e9afe58f56f782455cdd5f848`.
- Recorded failure under investigation: `job-20261104-163558-9b09a6a8`.
- Prior diagnostic Run: `41925699314`. Its logs could not be fetched here.

The trusted main AGENTS.md, Path 3 and Embedded contracts match candidate
versions byte for byte. Common and Manager contracts were also read. Latest
remote main could not be independently refreshed: `.git/FETCH_HEAD` is
read-only, and `git ls-remote` cannot resolve `github.com`. GitHub CLI has no
GH_TOKEN in the child environment. Do not retrieve parent-process credentials.

The enrolled credential/host-key helper completed successfully without printing
secrets. GET of the exact Job on the enrolled Gateway raised `PermissionError`
in this sandbox. No Job response was obtained. SSH and remote journal reads
were NOT_RUN; no alternative route, sandbox bypass or privilege escalation
was attempted. This is an executor access blocker, not a Gateway error code.

The Work Order reports native Worker Python
`/opt/plasma/python/3.12.13/bin/python3`, Site 2 SEALED, no OpenOCD process,
and no active Job or lease. These are supplied prior observations, not newly
verified state. Interpreter replacement is not justified. SEALED and absence of
OpenOCD do not establish successful SAFE_OFF or identify why the Job failed.

Source observations (not diagnoses of the recorded Job):

- `plasma_server/job_manager.py` emits `result.error` and attempt histories.
  The old snapshot omitted these; absence in that snapshot was not absence
  of a recorded error.
- `plasma_interfaces/site_worker_c3.py` maps C3 refusals to protocol errors,
  retaining `site_worker_stage`, `site_worker_code`, and `outcome_unknown` in
  context. A generic `E5002` alone cannot identify Root Admission, OpenOCD,
  or SAFE_OFF as the failing layer.
- `scripts/ppu_site_worker.py` seals on unknown transport outcomes and adapter
  exceptions, and rejects sealed Sites. The seal alone cannot distinguish
  these branches or startup sealing. No guard or seal behavior changed.
- The repair separately projects nested result errors and both attempt
  histories, with allowlisted C3 context and recorded result/code/safe_off.
  Missing evidence stays NOT_RECORDED; free-text messages, raw logs,
  exceptions and arbitrary context are omitted.

Changed source: `scripts/plasma_site2_job_error_snapshot.py`.
New regression tests: `software/python/tests/test_plasma_site2_job_error_snapshot.py`.
This document records acceptance limits. Changes remain uncommitted for the
existing trusted publisher; no new commit SHA or published PR HEAD is claimed.

Validation:

- PASS: 22 host tests (12 new snapshot tests plus 10 existing preflight tests),
  using `/tmp/plasma-ppu-trust-gate1a-venv/bin/python -m pytest -q
  software/python/tests/test_plasma_site2_job_error_snapshot.py
  software/python/tests/test_plasma_site2_path2_preflight.py`.
  Final run: 0.17 seconds. JUnit and log retained in
  `.plasma-path3-evidence/site2-host-tests.xml` and `site2-host.test.log`.
- PASS: `git diff --check`.
- FAIL / environment blocked: broader pre-final-projection suite including
  `test_c3_rest_flash_cycle.py` and `test_ppu_stage_c3_site_worker.py`:
  59 passed, 17 failed, 29 errors. Unix socket bind raises PermissionError
  (EPERM); loopback TCP listeners cannot bind. A narrowed diagnostic rerun
  recorded 49 passed / 7 failed, all seven REST cycle failures at listener
  setup, in `site2-diagnostic.test.log` and `site2-diagnostic-tests.xml`.
  These socket tests must run on a permitted host/CI; they do not prove HIL.
- System Python and native `/opt/plasma/python/3.12.13/bin/python3` lack pytest;
  no dependency install or runtime change attempted.
- NOT_RUN: required hosted CI, live PR status/reviews/threads/rulesets,
  real flash error/stage determination, fresh SAFE_OFF/ownership verification.
- NOT_RUN: second POST/Flash, unseal/recovery, deployment, service restart,
  FPGA load, DUT activity, merge. No hardware state change was requested.

Next bounded diagnostic: use the enrolled Path 2 read-only route on a permitted
executor to retrieve the exact prior Run/Job logs and GET this exact Job with
this repaired projection at its newly published pinned SHA. If the Job has
expired, inspect retained runtime/Worker/Root/OpenOCD logs for the original
Job time window, plus read-only seal reason and current ownership. Correlate
Gateway error, C3 stage/code, Root Admission decision, OpenOCD result and explicit
SAFE_OFF receipt separately. Do not call the admission diagnostic (it invokes
admit/revoke), recovery, POST or Flash. Record redacted evidence and hashes.
No root-cause runtime repair is justified until those observations are obtained.

Next Gate: Gate 2 only after actual diagnosis, scoped repair if warranted,
required CI and exact published HEAD review. This evidence is not merge-ready.
