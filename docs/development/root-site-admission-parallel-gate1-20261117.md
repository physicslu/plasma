# PLASMA Root Site Admission — parallel Site / hash dedup Gate 1 (2026-11-17)

**Status:** Draft PR, Host-only implementation candidate. No Gate 2, no deployment, no Z2/DUT operation.
**Baseline:** `main@aaacc16a80c0aa8e47c44c76186b09c2eca010ba` (post-#1470).
**Authority:** AGENTS.md, ADR-0007, Embedded/FPGA contracts. Retain Root Guard; no additional FPGA loader or Site execution engine.

## Before/after LOC baseline

Physical LOC counts include comments/blank lines, exclude terminal empty line. File-count scope is fixed; test and documentation lines are reported separately.

| File / fixed scope | Before | Gate 1 candidate | Delta |
| --- | ---: | ---: | ---: |
| `scripts/z2/plasma_swd_site_admission.py` | 225 | 240 | +15 |
| `pl/hil/fpga_image_guard.py` | 583 | 595 | +12 |
| `pl/hil/fpga_image_root.py` | 1219 | 1220 | +1 |
| `pl/hil/fpga_image_admission.py` | 207 | 207 | 0 |
| **Four core Root modules** | **2234** | **2262** | **+28** |
| Eight production files from baseline (including Adapter/Native C/Site Worker) | 4309 | 4337 | +28 |

Added lines are mainly measured-stage diagnostics and a comment; this PR does **not** claim net LOC reduction. Its actual deletion is the redundant two on-disk hash passes in the Site hot path and the cross-Site exclusive admission bottleneck. Deletion-first follow-up requires exact measured evidence and invariants.

## Changes

1. `RootZ2TargetPort.exclusive(site=N)` takes `supervisor.lock` **SH** with a bounded wait, not **EX**. Maintenance and FPGA Download/Restore still take supervisor **EX**. All admitted Site paths still take PPU Reload Fence **SH** and their own Site **EX**; Reload obtains PPU Fence **EX**. Existing protected admission records cover admission-to-OpenOCD attach gaps.
2. `live_site_admission_report` trusts `collect_live/check_exact`'s same-transaction SHA256 evidence for the Candidate and Golden Images. It does not rehash both files a second time; the underlying first hashes, file provenance checks, Root journal and fail-closed validations remain.
3. Successful `admit` outputs additive `timing_ms` diagnostics: `preflight`, `lock_and_fence`, `root_journal`, `image_hash`, `kernel_owners`, `process_census`, `live_report`, `record_commit` and `total`. Timings are measured with `time.monotonic_ns()`; `lock_and_fence` includes acquiring/configuring the fence and locks (not pure wait time). The protected on-disk `plasma.swd.ps-admission.v3` record format is **unchanged**. Numeric timing observations cannot grant hardware authority.
4. No new API, Batch scheduler, Provider, FPGA RTL, or Profile behavior. No /proc census removal, no unchecked image caching, no Site seal bypass and no implicit retry.

## Verification requirements and evidence boundary

- Focused Host-only tests: independent admissions **overlap** under supervisor SH, same-Site second owner denied, FPGA Reload EX denied while either Site is active/record remains; Site admissions denied while Reload EX; source/mapping conflicts still fail closed.
- Linux `flock` is cooperative; a privileged external bypass and active FPGA hardware cannot be proved away by mocks.
- Python/Native/Root hosted CI is needed on the exact Draft PR HEAD. Until it completes, all results are **NOT_RUN**.
- Z2 hardware timing and 2-Site HIL are **NOT_RUN**. The historic WP-07 ~6 s serialized Root Admission is a before-only approximate observation, not a per-stage baseline.
- Before Gate 2: inspect source/CI failures, negative tests, CI required contexts, then compare LOC and trace timing. Do not merge/deploy without separate owner Gate 2.
