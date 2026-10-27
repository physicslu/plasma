# Path 3 Cross-Job Resume — historical CPU-only Gate 1 (retired)

> **HISTORICAL ONLY.** This is an archival summary of the 2026-10-23
> `page-boundary-off-by-one` experiment. **Do not use it as a current Path 3
> Work Order, Dispatcher, workflow, CI acceptance or operator contract.**

## Historical scope and evidence

- The experimental path used Issue #981, a synthetic CPU-only page-splitting
  fixture, a first Codex Job that observed an expected failing test, and a
  second `development-codex-resume` Job intended to resume the same session.
- It was tied to exact owner/source/work-order identity and private session
  state; it granted **no** USB, SWPC hardware, FPGA, Z2, DUT, programming or
  deployment authority.
- PR #1134 had a one-time deferred SWPC two-Job acceptance exception.
  GitHub-hosted mock tests were not evidence of real cross-Job resumption;
  that SWPC two-Job acceptance was **NOT_RUN** in the historical record.
- A separate manually invoked two-process, host-only probe has
  **OWNER_REPORTED_PASS** evidence, not independently verified real cross-Job
  Runner acceptance. See
  [historical offline research PoC](plasma-path3-session-resume-host-only-poc.md).

## Current disposition (main after PR #1181, 2026-10-27)

- The `session_resume` Work Order field and Cross-Job Resume Dispatcher branch
  are retired; the current Dispatcher rejects the obsolete field.
- The `development-codex-resume` workflow Job and
  `scripts/plasma_path3_cross_job_resume.py` runtime Adapter were deleted.
- `scripts/plasma_path3_session_resume_probe.py` is retained solely as an
  **offline, manual CPU-only research fixture**, with fake-Codex unit tests.
  It is **not** invoked or imported by the live Path 3 Dispatcher/workflow.
- Ordinary Path 3 uses the generic owner/SHA-gated Codex Job and native tools.
  Hardware ownership, OS permissions, device mutex and FPGA Root Guard remain
  independently enforced; this document grants no operational authorization.

For the current contract, see
[Path 3 direct hardware tools](plasma-path3-direct-hardware-tools.md),
[three-path execution model](plasma-three-path-execution-model.md), and
[PR #1181](https://github.com/physicslu/plasma/pull/1181).
