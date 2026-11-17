# PLASMA #1469 Post-merge CI Regression — Gate 1 Work Order (2026-11-17)

## Authorization and boundaries

Owner instruction: 「請繼續修改到Gate2」 following the failed post-merge verification of PR #1469. **Gate 1 scope: repair observed regression failures, run real Host-only/CI acceptance, and deliver a new Draft PR ready for a separate owner Gate 2 merge decision.** This does not authorize merging, installing/deploying on SWPC/Z2, touching DUT/FPGA, changing `reset run` behavior, implementing Repeat, changing electrical safety, relaxing actual security/admission, or bypassing CI approval.

Base: `main@b3cd58d3dc86667a1b9c708ecd943ec84b8d94d7` (squash merge of #1469). Follow AGENTS.md, Path 3 and applicable domain contracts. Preserve verified Bundle v3, explicit `programming + operations[]`, independent `read`, no `flash_cycle` fallback, Job Binding, 8-Site concurrency/isolation, SAFE_OFF, Resource Set, exact admission, accepted-Job drain, durable journaling, OUTCOME_UNKNOWN no-blind-retry.

## Verified post-merge failures

### Python PS source tests — GitHub Actions [Run #43985583935](https://github.com/physicslu/plasma/actions/runs/43985583935)

`test` Job failed; `swd-openocd-native` Job passed. Pytest summary: **3 failed, 4,284 passed, 12 skipped, 1 warning, 4,571 subtests passed**.

1. `software/python/tests/test_ppu_gateway_catalog_free.py::test_bundle_target_provider_negatives_hold_with_selector_absent[catalog-qualified-target-without-bundle-REFERENCE_TARGET_MISMATCH]`: expected downstream `REFERENCE_TARGET_MISMATCH`, actual prior fail-closed `job_binding does not match this Job request` (HTTP 400). Check fixture's exact `programming operations[]` / Binding and negative test layer. Do not bypass Gateway Binding checks just to hit a later error.
2. Same test `[no-active-set-OPF_ACTIVE_SET_REQUIRED]`: expected `OPF_ACTIVE_SET_REQUIRED`, actual fail-closed `JOB_RESOURCE_NOT_ACTIVE` E4005. Determine correct normative boundary/error and assert non-execution; don't automatically force a legacy code.
3. `software/python/tests/test_programming_batch_lanes.py::test_shared_failure_stops_global_admission_and_observes_accepted_job`: 10-second wait for shared-failure latch timed out. Diagnose concurrency/barrier/generator ordering and shared failure behavior; ensure accepted Job is observed/drained and all new global admission stops. Do not merely enlarge WAIT to conceal a race.

### Web validation — GitHub Actions [Run #43985583562](https://github.com/physicslu/plasma/actions/runs/43985583562)

`test` Job passed. Playwright `e2e` Job failed after **15-minute workflow timeout** during 204 tests, with repeated EMode `START PROGRAMMING` disabled and many `Read SITE 2 Flash` locator-not-found errors in `software/web/e2e/tests/emode-managed-programming.spec.ts` (among them lines ~713, 735, 764, 787, 821, 846, 892, 934, 951). Identify earliest shared cause and differentiate invalid stale UI/mock fixtures vs real UI regression. Keep EMode/PMode behavioral and safety gates. Fix production code only where proven required. Run focused Playwright E2E before broad suite; no timeout inflation or mass test suppression.

### Positive baseline

Post-merge SHA had SUCCESS in Repository contracts, Mock CD, Mock CD Browser Runtime Acceptance, z2like-demo QEMU ARMv7, PPU bootstrap regression, Control Station runtime packaging, macOS installer, Z2 PS release candidate, z2like-demo Browser live acceptance. These are **not** substitute evidence for failed Python/Web suites or actual Z2/DUT HIL.

## Required evidence / Gate 2 checklist

1. Independently identify concrete root cause(s), callers and current contracts before edits. Inventory other open PR overlap.
2. Make smallest in-scope fix, update test fixtures only when their expectation is genuinely obsolete, and prove safety negative cases still fail closed. Keep real regressions fixed in source.
3. Run focused Python tests; all Python PS Source Tests on GitHub; focused Web E2E, full Playwright E2E + normal Web validation; relevant Bundle/PPU/Batch failure tests and CI. Capture exact test commands, pass/fail/skip counts, logs/artifacts, final SHA, any CI `action_required`/manual workflow authorization.
4. Ensure `programming + operations[]`, one Job/Binding, READ independent, concurrency/site failure isolation, SAFE_OFF, Accepted-Job drain, unknown-outcome/no resend. Do not reintroduce `flash_cycle` or change Target Finalization/Repeat.
5. Update TODO's stale PR #1469 "Draft / Gate 2 not approved" claim with truthful "merged; regression follow-up pending" and reference this corrective PR, if in scope and minimal.
6. Record reviewer-ready Gate 2 matrix: exact PR HEAD/CI check names and conclusions, changed files/LOC, thread resolution, mergeability; explicitly mark Z2 deployment and DUT HIL NOT_RUN. **Do not merge this PR; await Owner Gate 2.**
